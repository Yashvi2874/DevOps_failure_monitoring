"""Prometheus metrics exposed on /metrics.

Every app instance gets its own registry. That keeps the unit tests independent
of each other (no "duplicated timeseries" errors) and makes it obvious which
metrics belong to this service.
"""

from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    PlatformCollector,
    ProcessCollector,
)

SENSOR_LABELS = ["sensor", "location"]


class DashboardMetrics:
    def __init__(self, registry=None):
        self.registry = registry or CollectorRegistry()
        # process_start_time_seconds comes from here; the AppRestarted alert
        # uses it to notice crashes and redeploys.
        ProcessCollector(registry=self.registry)
        PlatformCollector(registry=self.registry)

        def gauge(name, doc, labels=SENSOR_LABELS):
            return Gauge(name, doc, labels, registry=self.registry)

        self.temperature = gauge("sensor_temperature_celsius", "Latest temperature reading (degrees C)")
        self.humidity = gauge("sensor_humidity_percent", "Latest relative humidity reading (%)")
        self.co2 = gauge("sensor_co2_ppm", "Latest CO2 reading (parts per million)")
        self.pm25 = gauge("sensor_pm25_ugm3", "Latest PM2.5 reading (micrograms per cubic metre)")
        self.last_seen = gauge("sensor_last_seen_timestamp_seconds", "Unix time of the last good reading")
        self.sensor_up = gauge("sensor_up", "1 while the sensor is reporting, 0 when it is offline")
        self.read_errors = Counter(
            "sensor_read_errors", "Failed sensor reads", SENSOR_LABELS, registry=self.registry
        )

        self.requests = Counter(
            "dashboard_http_requests",
            "HTTP requests handled by the dashboard",
            ["method", "endpoint", "status"],
            registry=self.registry,
        )
        self.latency = Histogram(
            "dashboard_http_request_duration_seconds",
            "Time spent handling HTTP requests",
            ["endpoint"],
            buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5),
            registry=self.registry,
        )
        self.build_info = Gauge(
            "dashboard_build_info",
            "Always 1; the labels say which build is running",
            ["version", "commit", "build"],
            registry=self.registry,
        )
        self._reported_errors = {}

    def set_build_info(self, version, commit, build):
        self.build_info.labels(version=version, commit=commit, build=build).set(1)

    def update(self, sensors):
        """Copy a simulator snapshot into the gauges."""
        for s in sensors:
            labels = {"sensor": s["id"], "location": s["location"]}
            values = s["values"]
            self.temperature.labels(**labels).set(values["temperature"])
            self.humidity.labels(**labels).set(values["humidity"])
            self.co2.labels(**labels).set(values["co2"])
            self.pm25.labels(**labels).set(values["pm25"])
            self.last_seen.labels(**labels).set(s["last_seen"])
            self.sensor_up.labels(**labels).set(1 if s["online"] else 0)

            # The simulator keeps a running total; a Counter only goes up, so
            # add whatever is new since the last update. Calling labels() even
            # when nothing changed makes the series show up as 0 from the start.
            errors = self.read_errors.labels(**labels)
            new_errors = s["read_errors"] - self._reported_errors.get(s["id"], 0)
            if new_errors > 0:
                errors.inc(new_errors)
            self._reported_errors[s["id"]] = s["read_errors"]
