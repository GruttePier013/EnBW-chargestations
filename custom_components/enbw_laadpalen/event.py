"""Event entity per station: fires when a charge point becomes available while someone is in the zone."""

from __future__ import annotations

from typing import Any

from homeassistant.components.event import EventEntity
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import EVENT_CHARGE_POINT_AVAILABLE
from .coordinator import EnbwConfigEntry
from .sensor import EnbwEntity

EVENT_TYPE = "charge_point_available"


async def async_setup_entry(
    hass: HomeAssistant, entry: EnbwConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities(ChargePointEvent(c) for c in entry.runtime_data.coordinators.values())


class ChargePointEvent(EnbwEntity, EventEntity):
    """Mirrors the ``enbw_laadpalen_charge_point_available`` bus event of this station.

    The bus event is fired only for charge points that went from occupied to available while at
    least one tracked person is inside the zone of the station.
    """

    _attr_event_types = [EVENT_TYPE]
    _attr_icon = "mdi:ev-plug-type2"
    # keep the event type attribute in the recorder (the logbook needs it)
    _unrecorded_attributes = frozenset({"persons", "connectors"})

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "charge_point_event")

    @property
    def available(self) -> bool:
        return True

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        station_id = self.coordinator.station_id

        @callback
        def _matches(data: Any) -> bool:
            return data.get("station_id") == station_id

        self.async_on_remove(
            self.hass.bus.async_listen(EVENT_CHARGE_POINT_AVAILABLE, self._handle_event, event_filter=_matches)
        )

    @callback
    def _handle_event(self, event: Event) -> None:
        self._trigger_event(EVENT_TYPE, dict(event.data))
        self.async_write_ha_state()
