from custom_components.enbw_charging_stations.schedules import DEFAULT_SCHEDULE, fires_at


def test_schedules():
    assert DEFAULT_SCHEDULE == "never" and not fires_at("never", 6, 0)
    assert fires_at("every_15_min", 13, 45) and not fires_at("every_15_min", 13, 40)
    assert fires_at("every_5_min_rush", 9, 0) and not fires_at("every_5_min_rush", 12, 0)


def test_zone_settings():
    from custom_components.enbw_charging_stations.schedules import (
        DEFAULT_ZONE_INTERVAL,
        DEFAULT_ZONE_STOP_AFTER,
        ZONE_INTERVALS,
        ZONE_STOP_AFTER,
    )

    assert DEFAULT_ZONE_INTERVAL == "every_5_min" and ZONE_INTERVALS["on_entry"] is None
    assert [ZONE_INTERVALS[k] for k in ("every_2_min", "every_5_min", "every_10_min", "every_15_min")] == [2, 5, 10, 15]
    assert DEFAULT_ZONE_STOP_AFTER == "30_min" and ZONE_STOP_AFTER["unlimited"] is None
