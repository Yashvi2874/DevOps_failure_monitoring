"""Flask app: the dashboard page, a small JSON API and the /metrics endpoint."""

import json
import os
import signal
import threading
import time
import urllib.error
import urllib.request
from types import SimpleNamespace

from flask import Flask, Response, g, jsonify, render_template, request
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from .metrics import DashboardMetrics
from .sensors import SCENARIOS, SamplerThread, SensorSimulator

SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2}


def env_flag(name, default=False):
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def crash_process():
    """Stop the whole container, not just this worker.

    In the container gunicorn runs as PID 1 and this worker is its child.
    Interrupting gunicorn makes the container exit, and Docker's restart
    policy brings it back, which is what a real crash plus recovery looks
    like. Outside a container we only exit our own process.
    """
    if os.getppid() == 1:
        os.kill(1, signal.SIGINT)
    os._exit(1)


def create_app(config=None):
    app = Flask(__name__)
    app.config.update(
        ENABLE_SIMULATION=env_flag("ENABLE_SIMULATION", True),
        FORCE_UNHEALTHY=env_flag("FORCE_UNHEALTHY", False),
        ALERTMANAGER_URL=os.environ.get("ALERTMANAGER_URL", "").rstrip("/"),
        SAMPLE_INTERVAL=float(os.environ.get("SAMPLE_INTERVAL", "2")),
        START_SAMPLER=True,
        SEED=None,
        APP_VERSION=os.environ.get("APP_VERSION", "dev"),
        GIT_COMMIT=os.environ.get("GIT_COMMIT", "unknown"),
        BUILD_NUMBER=os.environ.get("BUILD_NUMBER", "local"),
        CRASH_FUNCTION=crash_process,
    )
    if config:
        app.config.update(config)

    simulator = SensorSimulator(seed=app.config["SEED"])
    metrics = DashboardMetrics()
    build = {
        "version": app.config["APP_VERSION"],
        "commit": app.config["GIT_COMMIT"],
        "build": app.config["BUILD_NUMBER"],
    }
    metrics.set_build_info(**build)
    state = SimpleNamespace(api_errors=False, started_at=time.time())

    def refresh_metrics():
        metrics.update(simulator.snapshot())

    refresh_metrics()
    sampler = None
    if app.config["START_SAMPLER"]:
        sampler = SamplerThread(simulator, refresh_metrics, app.config["SAMPLE_INTERVAL"])
        sampler.start()

    app.extensions["sensor_dashboard"] = SimpleNamespace(
        simulator=simulator, metrics=metrics, state=state, sampler=sampler, build=build
    )

    # ---- request metrics -------------------------------------------------

    @app.before_request
    def start_timer():
        g.start_time = time.perf_counter()

    @app.after_request
    def record_request(response):
        # Use the route pattern, not the raw path, so /static/<anything>
        # doesn't create a new time series for every file.
        endpoint = request.url_rule.rule if request.url_rule else "unmatched"
        metrics.requests.labels(request.method, endpoint, str(response.status_code)).inc()
        if "start_time" in g:
            metrics.latency.labels(endpoint).observe(time.perf_counter() - g.start_time)
        return response

    # ---- pages -------------------------------------------------------------

    @app.get("/")
    def index():
        return render_template(
            "index.html", build=build, simulation=app.config["ENABLE_SIMULATION"]
        )

    @app.get("/health")
    def health():
        if app.config["FORCE_UNHEALTHY"]:
            return jsonify(status="unhealthy", reason="FORCE_UNHEALTHY is set"), 503
        sensors = simulator.snapshot()
        return jsonify(
            status="ok",
            sensors_online=sum(1 for s in sensors if s["online"]),
            sensors_total=len(sensors),
            uptime_seconds=round(time.time() - state.started_at, 1),
            build=build,
        )

    @app.get("/metrics")
    def prometheus_metrics():
        return Response(generate_latest(metrics.registry), mimetype=CONTENT_TYPE_LATEST)

    # ---- JSON API ----------------------------------------------------------

    @app.get("/api/readings")
    def readings():
        if state.api_errors:
            return jsonify(error="simulated API failure"), 500
        return jsonify(sensors=simulator.snapshot(), build=build, generated_at=time.time())

    @app.get("/api/simulation")
    def simulation_state():
        return jsonify(
            enabled=app.config["ENABLE_SIMULATION"],
            api_errors=state.api_errors,
            sensors={s["id"]: s["scenarios"] for s in simulator.snapshot()},
        )

    @app.post("/api/simulate/<scenario>")
    def simulate(scenario):
        if not app.config["ENABLE_SIMULATION"]:
            return jsonify(error="failure simulation is disabled"), 403

        body = request.get_json(silent=True) or {}
        active = bool(body.get("active", True))

        if scenario == "reset":
            simulator.reset()
            state.api_errors = False
        elif scenario == "api-errors":
            state.api_errors = active
        elif scenario == "crash":
            # Answer first, then die, so the button gets a response.
            threading.Timer(0.5, app.config["CRASH_FUNCTION"]).start()
            return jsonify(ok=True, scenario="crash", message="crashing in 0.5s")
        elif scenario in SCENARIOS:
            sensor_id = body.get("sensor")
            if sensor_id not in simulator.sensors:
                return jsonify(error=f"unknown sensor: {sensor_id}"), 404
            simulator.set_scenario(sensor_id, scenario, active)
        else:
            return jsonify(error=f"unknown scenario: {scenario}"), 400

        refresh_metrics()
        return jsonify(ok=True, scenario=scenario, active=active)

    @app.get("/api/alerts")
    def active_alerts():
        """Show Alertmanager's active alerts on the dashboard itself."""
        base = app.config["ALERTMANAGER_URL"]
        if not base:
            return jsonify(available=False, alerts=[], reason="ALERTMANAGER_URL not set")
        url = f"{base}/api/v2/alerts?active=true&silenced=false&inhibited=false"
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                raw = json.load(resp)
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            return jsonify(available=False, alerts=[], reason=str(exc))

        alerts = [
            {
                "name": a["labels"].get("alertname", "unknown"),
                "severity": a["labels"].get("severity", "info"),
                "sensor": a["labels"].get("sensor"),
                "summary": a.get("annotations", {}).get("summary", ""),
                "starts_at": a.get("startsAt"),
            }
            for a in raw
        ]
        alerts.sort(key=lambda a: (SEVERITY_ORDER.get(a["severity"], 9), a["name"]))
        return jsonify(available=True, alerts=alerts)

    return app
