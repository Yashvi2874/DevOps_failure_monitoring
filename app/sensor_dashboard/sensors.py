"""Simulated environmental sensors.

Each sensor does a mean-reverting random walk around its own baseline, so the
numbers move like real readings instead of jumping around. Failure scenarios
(overheat, offline, pollution) can be switched on per sensor so that the
monitoring stack has something real to detect during a demo.
"""

import random
import threading
import time
from dataclasses import dataclass, field

# Physical limits, used to clamp values so a long random walk never produces
# something silly like negative humidity.
LIMITS = {
    "temperature": (-10.0, 60.0),
    "humidity": (5.0, 100.0),
    "co2": (350.0, 5000.0),
    "pm25": (0.0, 500.0),
}

# How much each value wobbles per tick.
NOISE = {"temperature": 0.25, "humidity": 0.8, "co2": 12.0, "pm25": 1.5}

# Where a value drifts towards while a failure scenario is active.
OVERHEAT_TARGET = 45.0
POLLUTION_TARGETS = {"co2": 2200.0, "pm25": 180.0}

SCENARIOS = ("overheat", "offline", "pollution")


@dataclass
class Sensor:
    sensor_id: str
    name: str
    location: str
    baseline: dict
    values: dict = field(default_factory=dict)
    scenarios: set = field(default_factory=set)
    last_seen: float = 0.0
    read_errors: int = 0
    history: list = field(default_factory=list)

    @property
    def online(self):
        return "offline" not in self.scenarios

    def target(self, metric):
        if metric == "temperature" and "overheat" in self.scenarios:
            return OVERHEAT_TARGET
        if metric in POLLUTION_TARGETS and "pollution" in self.scenarios:
            return POLLUTION_TARGETS[metric]
        return self.baseline[metric]

    def to_dict(self, now=None):
        now = time.time() if now is None else now
        return {
            "id": self.sensor_id,
            "name": self.name,
            "location": self.location,
            "online": self.online,
            "scenarios": sorted(self.scenarios),
            "values": {k: round(v, 1) for k, v in self.values.items()},
            "last_seen": self.last_seen,
            "seconds_since_update": round(now - self.last_seen, 1),
            "read_errors": self.read_errors,
            "history": list(self.history),
        }


def default_sensors():
    return [
        Sensor("sensor-1", "Sensor 1", "Lab",
               {"temperature": 23.0, "humidity": 45.0, "co2": 620.0, "pm25": 14.0}),
        Sensor("sensor-2", "Sensor 2", "Server room",
               {"temperature": 26.0, "humidity": 38.0, "co2": 520.0, "pm25": 9.0}),
        Sensor("sensor-3", "Sensor 3", "Outdoors",
               {"temperature": 30.0, "humidity": 62.0, "co2": 425.0, "pm25": 48.0}),
    ]


class SensorSimulator:
    """Owns the sensors and moves their readings forward one tick at a time."""

    HISTORY_LENGTH = 60

    def __init__(self, sensors=None, seed=None, clock=time.time):
        self._rng = random.Random(seed)
        self._clock = clock
        self._lock = threading.Lock()
        self.sensors = {s.sensor_id: s for s in (sensors or default_sensors())}
        now = self._clock()
        for sensor in self.sensors.values():
            sensor.values = dict(sensor.baseline)
            sensor.last_seen = now

    def tick(self):
        """Take one reading from every sensor that is online."""
        now = self._clock()
        with self._lock:
            for sensor in self.sensors.values():
                if not sensor.online:
                    sensor.read_errors += 1
                    continue
                for metric, value in sensor.values.items():
                    target = sensor.target(metric)
                    # Drift faster towards a failure target so alerts show up
                    # within a few seconds instead of minutes.
                    pull = 0.25 if target != sensor.baseline[metric] else 0.1
                    value += (target - value) * pull
                    value += self._rng.gauss(0, NOISE[metric])
                    low, high = LIMITS[metric]
                    sensor.values[metric] = min(max(value, low), high)
                sensor.last_seen = now
                sensor.history.append(round(sensor.values["temperature"], 2))
                del sensor.history[:-self.HISTORY_LENGTH]

    def set_scenario(self, sensor_id, scenario, active=True):
        if scenario not in SCENARIOS:
            raise ValueError(f"unknown scenario: {scenario}")
        with self._lock:
            sensor = self.sensors[sensor_id]  # KeyError for unknown sensors
            if active:
                sensor.scenarios.add(scenario)
            else:
                sensor.scenarios.discard(scenario)

    def reset(self):
        with self._lock:
            for sensor in self.sensors.values():
                sensor.scenarios.clear()

    def snapshot(self):
        now = self._clock()
        with self._lock:
            return [s.to_dict(now) for s in self.sensors.values()]


class SamplerThread(threading.Thread):
    """Background thread that ticks the simulator and refreshes the metrics."""

    def __init__(self, simulator, on_tick, interval=2.0):
        super().__init__(name="sensor-sampler", daemon=True)
        self.simulator = simulator
        self.on_tick = on_tick
        self.interval = interval
        self._stop_event = threading.Event()

    def run(self):
        while not self._stop_event.is_set():
            self.simulator.tick()
            self.on_tick()
            self._stop_event.wait(self.interval)

    def stop(self):
        self._stop_event.set()
