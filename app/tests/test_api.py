import json
from unittest import mock

import pytest

from sensor_dashboard import create_app


@pytest.fixture
def crash():
    return mock.Mock()


@pytest.fixture
def app(crash):
    return create_app({
        "TESTING": True,
        "START_SAMPLER": False,
        "SEED": 1,
        "ENABLE_SIMULATION": True,
        "FORCE_UNHEALTHY": False,
        "ALERTMANAGER_URL": "",
        "BUILD_NUMBER": "17",
        "GIT_COMMIT": "abc1234",
        "CRASH_FUNCTION": crash,
    })


@pytest.fixture
def client(app):
    return app.test_client()


def test_health_reports_ok(client):
    res = client.get("/health")
    assert res.status_code == 200
    body = res.get_json()
    assert body["status"] == "ok"
    assert body["sensors_online"] == 3
    assert body["build"]["build"] == "17"


def test_health_fails_when_forced(crash):
    app = create_app({"START_SAMPLER": False, "FORCE_UNHEALTHY": True, "CRASH_FUNCTION": crash})
    res = app.test_client().get("/health")
    assert res.status_code == 503


def test_dashboard_page_renders(client):
    res = client.get("/")
    assert res.status_code == 200
    page = res.get_data(as_text=True)
    assert "Environmental Sensor Dashboard" in page
    assert "build #17" in page


def test_readings_api_returns_three_sensors(client):
    res = client.get("/api/readings")
    assert res.status_code == 200
    sensors = res.get_json()["sensors"]
    assert len(sensors) == 4  # deliberately wrong: there are 3 sensors
    for s in sensors:
        assert set(s["values"]) == {"temperature", "humidity", "co2", "pm25"}


def test_metrics_endpoint_exposes_sensor_and_build_metrics(client):
    client.get("/api/readings")
    res = client.get("/metrics")
    assert res.status_code == 200
    text = res.get_data(as_text=True)
    for name in (
        "sensor_temperature_celsius",
        "sensor_humidity_percent",
        "sensor_co2_ppm",
        "sensor_pm25_ugm3",
        "sensor_last_seen_timestamp_seconds",
        "sensor_up",
        "sensor_read_errors_total",
        "dashboard_http_requests_total",
        'dashboard_build_info{build="17",commit="abc1234"',
    ):
        assert name in text, name


def test_request_counter_uses_route_pattern(client):
    client.get("/api/readings")
    text = client.get("/metrics").get_data(as_text=True)
    assert 'endpoint="/api/readings"' in text


def post(client, scenario, **body):
    return client.post(f"/api/simulate/{scenario}", data=json.dumps(body),
                       content_type="application/json")


def test_overheat_scenario_can_be_switched_on_and_off(client):
    assert post(client, "overheat", sensor="sensor-1").status_code == 200
    state = client.get("/api/simulation").get_json()
    assert state["sensors"]["sensor-1"] == ["overheat"]

    post(client, "overheat", sensor="sensor-1", active=False)
    assert client.get("/api/simulation").get_json()["sensors"]["sensor-1"] == []


def test_offline_scenario_sets_sensor_up_to_zero(client):
    post(client, "offline", sensor="sensor-2")
    text = client.get("/metrics").get_data(as_text=True)
    assert 'sensor_up{location="Server room",sensor="sensor-2"} 0.0' in text


def test_api_errors_make_readings_fail(client):
    post(client, "api-errors", active=True)
    assert client.get("/api/readings").status_code == 500
    post(client, "reset")
    assert client.get("/api/readings").status_code == 200


def test_unknown_sensor_and_scenario_are_rejected(client):
    assert post(client, "overheat", sensor="sensor-9").status_code == 404
    assert post(client, "earthquake").status_code == 400


def test_simulation_can_be_disabled(crash):
    app = create_app({"START_SAMPLER": False, "ENABLE_SIMULATION": False, "CRASH_FUNCTION": crash})
    res = app.test_client().post("/api/simulate/reset")
    assert res.status_code == 403


def test_crash_answers_before_crashing(client, crash):
    with mock.patch("sensor_dashboard.app.threading.Timer") as timer:
        res = post(client, "crash")
    assert res.status_code == 200
    timer.assert_called_once_with(0.5, crash)
    timer.return_value.start.assert_called_once()


def test_alerts_endpoint_without_alertmanager(client):
    body = client.get("/api/alerts").get_json()
    assert body["available"] is False
    assert body["alerts"] == []


def test_alerts_endpoint_formats_alertmanager_response(crash):
    app = create_app({
        "START_SAMPLER": False,
        "ALERTMANAGER_URL": "http://alertmanager:9093",
        "CRASH_FUNCTION": crash,
    })
    payload = [
        {"labels": {"alertname": "SensorOverheat", "severity": "warning", "sensor": "sensor-1"},
         "annotations": {"summary": "Lab is 41 C"}, "startsAt": "2026-10-02T10:00:00Z"},
        {"labels": {"alertname": "SensorDashboardDown", "severity": "critical"},
         "annotations": {"summary": "down"}, "startsAt": "2026-10-02T10:01:00Z"},
    ]
    fake = mock.MagicMock()
    fake.__enter__.return_value.read.return_value = json.dumps(payload).encode()
    with mock.patch("sensor_dashboard.app.urllib.request.urlopen", return_value=fake):
        body = app.test_client().get("/api/alerts").get_json()
    assert body["available"] is True
    # critical alerts are listed first
    assert [a["name"] for a in body["alerts"]] == ["SensorDashboardDown", "SensorOverheat"]
