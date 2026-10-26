"""Refresh buttons: one per station and one that refreshes all stations."""

from __future__ import annotations

import asyncio

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, NAME
from .coordinator import EnbwConfigEntry
from .sensor import EnbwEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: EnbwConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    entities: list[ButtonEntity] = [RefreshButton(c) for c in entry.runtime_data.coordinators.values()]
    entities.append(RefreshAllButton(entry))
    async_add_entities(entities)


class RefreshButton(EnbwEntity, ButtonEntity):
    """Fetches the current status right now (also resumes a station that paused after errors)."""

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "refresh")

    @property
    def available(self) -> bool:
        return True  # also usable to retry a failed or paused station

    async def async_press(self) -> None:
        await self.coordinator.async_manual_refresh()


class RefreshAllButton(ButtonEntity):
    """Refreshes every station of the integration (same as the ``enbw_laadpalen.refresh_all`` action)."""

    _attr_has_entity_name = True
    _attr_name = "Alle laadpalen vernieuwen"
    _attr_icon = "mdi:refresh-circle"

    def __init__(self, entry: EnbwConfigEntry) -> None:
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_refresh_all"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, entry.entry_id)}, name=NAME, manufacturer="EnBW")

    async def async_press(self) -> None:
        await asyncio.gather(*(c.async_manual_refresh() for c in self._entry.runtime_data.coordinators.values()))
