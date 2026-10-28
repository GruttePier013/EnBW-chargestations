"""Switches per station: refresh in zone (main switch) and approach-only refreshing."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import STATE_OFF, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import CONF_DEFAULT_APPROACH_ONLY, CONF_DEFAULT_REFRESH_ON_ZONE
from .coordinator import EnbwConfigEntry
from .defaults import get_defaults
from .sensor import EnbwEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: EnbwConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    for c in entry.runtime_data.coordinators.values():
        async_add_entities([RefreshOnApproach(c), ApproachOnly(c)])


class RefreshOnApproach(EnbwEntity, SwitchEntity, RestoreEntity):
    """Main switch for refreshing in the zone: on entry and (optionally) every X minutes while someone is in the zone."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "zone_refresh")
        self._attr_is_on = get_defaults(coordinator.entry.options)[CONF_DEFAULT_REFRESH_ON_ZONE]

    @property
    def available(self) -> bool:
        return True

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None:
            self._attr_is_on = last.state != STATE_OFF
        self.coordinator.refresh_on_approach = bool(self._attr_is_on)
        self.coordinator.apply_zone_settings()

    async def async_turn_on(self, **kwargs: Any) -> None:
        self._attr_is_on = True
        self.coordinator.refresh_on_approach = True
        self.coordinator.apply_zone_settings()
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        self._attr_is_on = False
        self.coordinator.refresh_on_approach = False
        self.coordinator.apply_zone_settings()
        self.async_write_ha_state()


class ApproachOnly(EnbwEntity, SwitchEntity, RestoreEntity):
    """Interval refreshes in the zone only happen while someone is getting closer to the station."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "zone_refresh_approach")
        self._attr_is_on = get_defaults(coordinator.entry.options)[CONF_DEFAULT_APPROACH_ONLY]

    @property
    def available(self) -> bool:
        return True

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None:
            self._attr_is_on = last.state != STATE_OFF
        self.coordinator.approach_only = bool(self._attr_is_on)

    async def async_turn_on(self, **kwargs: Any) -> None:
        self._attr_is_on = True
        self.coordinator.approach_only = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        self._attr_is_on = False
        self.coordinator.approach_only = False
        self.async_write_ha_state()
