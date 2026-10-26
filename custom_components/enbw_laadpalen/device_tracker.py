"""Location of the station (shown on the map with a picture that follows availability)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.device_tracker import SourceType, TrackerEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import PICTURE_AVAILABLE, PICTURE_PARTIAL, PICTURE_UNAVAILABLE, PICTURE_UNKNOWN
from .coordinator import EnbwConfigEntry
from .parser import picture_kind, summarize, visual_state
from .sensor import EnbwEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: EnbwConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities(StationLocation(c) for c in entry.runtime_data.coordinators.values() if c.location is not None)


class StationLocation(EnbwEntity, TrackerEntity):
    _attr_source_type = SourceType.GPS
    _attr_icon = "mdi:ev-station"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "location")

    @property
    def available(self) -> bool:
        return self.coordinator.location is not None

    @property
    def location_name(self) -> str:
        """State of the tracker: the same text as the 'Laadpunten' sensor, e.g. '2/4 beschikbaar'.

        Without this a GPS tracker shows its zone name ('not_home') in the more-info dialog.
        """
        c = self.coordinator
        return summarize(c.fresh_view)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Details shown in the attributes of the more-info dialog (not stored in the recorder)."""
        c = self.coordinator
        v = c.fresh_view
        if not v:
            return {}
        return {
            "available": v["free"],
            "total": v["total"],
            "visual": visual_state(v),
            "max_power_kw": v["max_power_kw"],
            "connector_types": v["plug_types"],
            "address": v["address"],
            "opening_hours": v["opening_hours"],
            "open": v["open"],
        }

    @property
    def entity_picture(self) -> str:
        """Green check = all charge points available, check + cross = some, red cross = none."""
        c = self.coordinator
        kind = picture_kind(c.view if c.last_update_success else None, c.is_stale)
        return {"available": PICTURE_AVAILABLE, "partial": PICTURE_PARTIAL, "unknown": PICTURE_UNKNOWN}.get(
            kind, PICTURE_UNAVAILABLE
        )

    @property
    def latitude(self) -> float | None:
        loc = self.coordinator.location
        return loc[0] if loc else None

    @property
    def longitude(self) -> float | None:
        loc = self.coordinator.location
        return loc[1] if loc else None
