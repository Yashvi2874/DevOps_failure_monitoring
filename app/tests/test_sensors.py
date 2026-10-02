import pytest

from sensor_dashboard.sensors import LIMITS, SensorSimulator


class FakeClock:
    def __init__(self, start=1_000_000.0):
        self.now = start

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def sim(clock):
    return SensorSimulator(seed=42, clock=clock)


def test_three_sensors_start_at_their_baseline(sim):
    sensors = sim.snapshot()
    assert [s["location"] for s in sensors] == ["Lab", "Server room", "Outdoors"]
    for s in sensors:
        assert s["online"]
        assert s["values"]["temperature"] < 35


def test_readings_stay_within_physical_limits(sim, clock):
    for _ in range(500):
        clock.advance(2)
        sim.tick()
    for s in sim.snapshot():
        for metric, value in s["values"].items():
            low, high = LIMITS[metric]
            assert low <= value <= high, f"{s['id']} {metric}={value}"


def test_normal_readings_stay_near_baseline(sim, clock):
    for _ in range(200):
        clock.advance(2)
        sim.tick()
    lab = sim.snapshot()[0]
    assert 18 < lab["values"]["temperature"] < 28


def test_overheat_pushes_temperature_over_the_alert_threshold(sim, clock):
    sim.set_scenario("sensor-1", "overheat")
    for _ in range(10):
        clock.advance(2)
        sim.tick()
    assert sim.snapshot()[0]["values"]["temperature"] > 35
    # the other sensors are not affected
    assert sim.snapshot()[1]["values"]["temperature"] < 35


def test_pollution_raises_co2_and_pm25(sim, clock):
    sim.set_scenario("sensor-3", "pollution")
    for _ in range(15):
        clock.advance(2)
        sim.tick()
    outdoors = sim.snapshot()[2]["values"]
    assert outdoors["co2"] > 1500
    assert outdoors["pm25"] > 100


def test_offline_sensor_stops_updating_and_counts_errors(sim, clock):
    sim.set_scenario("sensor-1", "offline")
    before = sim.snapshot()[0]["last_seen"]
    for _ in range(5):
        clock.advance(2)
        sim.tick()
    lab = sim.snapshot()[0]
    assert not lab["online"]
    assert lab["last_seen"] == before
    assert lab["seconds_since_update"] == 10
    assert lab["read_errors"] == 5


def test_reset_clears_every_scenario(sim):
    sim.set_scenario("sensor-1", "overheat")
    sim.set_scenario("sensor-2", "offline")
    sim.reset()
    assert all(s["scenarios"] == [] for s in sim.snapshot())


def test_unknown_scenario_is_rejected(sim):
    with pytest.raises(ValueError):
        sim.set_scenario("sensor-1", "earthquake")


def test_history_is_capped(sim, clock):
    for _ in range(SensorSimulator.HISTORY_LENGTH + 20):
        clock.advance(2)
        sim.tick()
    assert len(sim.snapshot()[0]["history"]) == SensorSimulator.HISTORY_LENGTH
