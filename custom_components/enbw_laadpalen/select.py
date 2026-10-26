"""Selects per station: refresh schedule, zone refresh frequency, zone stop-after (restored after restart)."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    CONF_DEFAULT_SCHEDULE,
    CONF_DEFAULT_ZONE_INTERVAL,
    CONF_DEFAULT_ZONE_STOP_AFTER,
)
from .coordinator import EnbwConfigEntry, StationCoordinator
from .defaults import get_defaults
from .schedules import (
    DEFAULT_SCHEDULE,
    DEFAULT_ZONE_INTERVAL,
    DEFAULT_ZONE_STOP_AFTER,
    SCHEDULES,
    ZONE_INTERVALS,
    ZONE_STOP_AFTER,
)
from .sensor import EnbwEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: EnbwConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    for c in entry.runtime_data.coordinators.values():
        async_add_entities([RefreshSchedule(c), ZoneRefreshFrequency(c), ZoneStopAfter(c)])


class RefreshSchedule(EnbwEntity, SelectEntity, RestoreEntity):
    """How often this station refreshes itself (besides the Refresh button)."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_options = list(SCHEDULES)

    def __init__(self, coordinator: StationCoordinator) -> None:
        super().__init__(coordinator, "refresh_schedule")
        self._attr_current_option = get_defaults(coordinator.entry.options)[CONF_DEFAULT_SCHEDULE]

    @property
    def available(self) -> bool:
        return True  # the schedule can be set even when EnBW does not answer

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last and last.state in SCHEDULES:
            self._attr_current_option = last.state
        self.coordinator.set_schedule(self._attr_current_option or DEFAULT_SCHEDULE)

    async def async_select_option(self, option: str) -> None:
        self._attr_current_option = option
        self.coordinator.set_schedule(option)
        self.async_write_ha_state()


class ZoneRefreshFrequency(EnbwEntity, SelectEntity, RestoreEntity):
    """How often the station refreshes while someone is in the zone (only when 'refresh in zone' is on).

    'on_entry' refreshes only at the moment someone enters the zone.
    """

    _attr_entity_category = EntityCategory.CONFIG
    _attr_options = list(ZONE_INTERVALS)

    def __init__(self, coordinator: StationCoordinator) -> None:
        super().__init__(coordinator, "zone_refresh")
        self._attr_current_option = get_defaults(coordinator.entry.options)[CONF_DEFAULT_ZONE_INTERVAL]

    @property
    def available(self) -> bool:
        return True

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last and last.state in ZONE_INTERVALS:
            self._attr_current_option = last.state
        self._apply()

    def _apply(self) -> None:
        self.coordinator.zone_interval_min = ZONE_INTERVALS[self._attr_current_option or DEFAULT_ZONE_INTERVAL]
        self.coordinator.apply_zone_settings()

    async def async_select_option(self, option: str) -> None:
        self._attr_current_option = option
        self._apply()
        self.async_write_ha_state()


class ZoneStopAfter(EnbwEntity, SelectEntity, RestoreEntity):
    """After how many minutes per visit refreshing in the zone stops (even if you are still there)."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_options = list(ZONE_STOP_AFTER)

    def __init__(self, coordinator: StationCoordinator) -> None:
        super().__init__(coordinator, "zone_stop_after")
        self._attr_current_option = get_defaults(coordinator.entry.options)[CONF_DEFAULT_ZONE_STOP_AFTER]

    @property
    def available(self) -> bool:
        return True

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last and last.state in ZONE_STOP_AFTER:
            self._attr_current_option = last.state
        self._apply()

    def _apply(self) -> None:
        self.coordinator.zone_stop_after_min = ZONE_STOP_AFTER[self._attr_current_option or DEFAULT_ZONE_STOP_AFTER]
        self.coordinator.apply_zone_settings()

    async def async_select_option(self, option: str) -> None:
        self._attr_current_option = option
        self._apply()
        self.async_write_ha_state()
