"""Post-deploy smoke test, run from a container on sensor-net:

    docker run --rm -i --network sensor-net -e EXPECTED_BUILD=42 \
        sensor-dashboard:42 python - < scripts/smoke_test.py

A non-zero exit fails the Jenkins stage and triggers the rollback.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request

APP = os.environ.get("APP_URL", "http://dashboard:8000")
PROMETHEUS = os.environ.get("PROMETHEUS_URL", "http://prometheus:9090")
EXPECTED_BUILD = os.environ.get("EXPECTED_BUILD", "")
TIMEOUT = float(os.environ.get("SMOKE_TIMEOUT", "45"))


def get(url):
    with urllib.request.urlopen(url, timeout=3) as resp:
        return resp.status, resp.read().decode()


def wait_for(description, check):
    deadline = time.time() + TIMEOUT
    last_problem = "not checked yet"
    while time.time() < deadline:
        try:
            ok, last_problem = check()
            if ok:
                print(f"PASS  {description}")
                return
        except (urllib.error.URLError, OSError, ValueError) as exc:
            last_problem = str(exc)
        time.sleep(2)
    print(f"FAIL  {description}: {last_problem}")
    sys.exit(1)


def health_ok():
    try:
        status, body = get(f"{APP}/health")
    except urllib.error.HTTPError as exc:
        return False, f"/health returned HTTP {exc.code}"
    data = json.loads(body)
    if status != 200 or data.get("status") != "ok":
        return False, f"/health said {body}"
    if EXPECTED_BUILD and data["build"]["build"] != EXPECTED_BUILD:
        return False, f"build {data['build']['build']} is running, expected {EXPECTED_BUILD}"
    return True, ""


def readings_ok():
    status, body = get(f"{APP}/api/readings")
    sensors = json.loads(body)["sensors"]
    return status == 200 and len(sensors) == 3, f"got {len(sensors)} sensors"


def metrics_ok():
    _, body = get(f"{APP}/metrics")
    return "sensor_temperature_celsius" in body, "sensor metrics missing from /metrics"


def prometheus_scrapes_app():
    _, body = get(f"{PROMETHEUS}/api/v1/targets")
    targets = json.loads(body)["data"]["activeTargets"]
    app = [t for t in targets if t["labels"].get("job") == "sensor-dashboard"]
    if not app:
        return False, "sensor-dashboard target not configured in Prometheus"
    return app[0]["health"] == "up", f"Prometheus sees the target as {app[0]['health']}"


if __name__ == "__main__":
    print(f"Smoke testing {APP} (expected build: {EXPECTED_BUILD or 'any'})")
    wait_for("app answers /health with status ok", health_ok)
    wait_for("API returns readings for 3 sensors", readings_ok)
    wait_for("/metrics exposes sensor metrics", metrics_ok)
    wait_for("Prometheus is scraping the new container", prometheus_scrapes_app)
    print("Smoke test passed")
