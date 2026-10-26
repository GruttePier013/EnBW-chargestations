"""Binary sensors: available, open, paused and one per charge point (occupied/free/unknown)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import EnbwConfigEntry, StationCoordinator
from .parser import point_name
from .sensor import EnbwEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: EnbwConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    for c in entry.runtime_data.coordinators.values():
        async_add_entities([Available(c), StationOpen(c), Paused(c)])
        known: set[str] = set()

        @callback
        def _add_points(c: StationCoordinator = c, known: set[str] = known) -> None:
            """One sensor per charge point; also when the points only appear at a later refresh."""
            new = []
            for index, p in enumerate((c.view or {}).get("all_points", []), start=1):
                uid = str(p["evse"] or index)
                if uid not in known:
                    known.add(uid)
                    new.append(ChargePointSensor(c, uid, p["evse"], index, p["power_kw"]))
            if new:
                async_add_entities(new)

        _add_points()
        entry.async_on_unload(c.async_add_listener(_add_points))


class Available(EnbwEntity, BinarySensorEntity):
    """On as soon as at least one (filtered) charge point is available and the station is not closed."""

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "available")

    @property
    def is_on(self) -> bool | None:
        v = self.coordinator.view
        if v is None:
            return None
        return v["free"] > 0 and v["open"] is not False

    @property
    def icon(self) -> str:
        return "mdi:ev-station" if self.is_on else "mdi:car-electric"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        v = self.coordinator.view
        return {"available": v["free"], "total": v["total"]} if v else {}


class StationOpen(EnbwEntity, BinarySensorEntity):
    _attr_entity_registry_enabled_default = False
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "open")

    @property
    def is_on(self) -> bool | None:
        v = self.coordinator.view
        return v["open"] if v else None

    @property
    def icon(self) -> str:
        return "mdi:door-open" if self.is_on else "mdi:door-closed"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        v = self.coordinator.view
        if not v:
            return {}
        return {
            "opening_hours": v["opening_hours"],
            "closed_on_holidays": v["closed_on_holidays"],
            "next_opening": v["next_opening"],
            "next_closing": v["next_closing"],
        }


class Paused(EnbwEntity, BinarySensorEntity):
    """On while this station has paused automatic refreshes after too many consecutive errors."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "paused")

    @property
    def available(self) -> bool:
        return True

    @property
    def is_on(self) -> bool:
        return self.coordinator.paused

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        c = self.coordinator
        return {
            "consecutive_errors": c.consecutive_errors,
            "max_errors": c.max_errors,
            "api_paused_for_s": round(c.api.blocked_for),
        }


class ChargePointSensor(EnbwEntity, BinarySensorEntity):
    """One charge point: on = occupied, off = free, unknown = out of service or no status.

    The display 'Bezet' / 'Vrij' comes from the translations (state translation of ``charge_point``).
    """

    _attr_device_class = BinarySensorDeviceClass.OCCUPANCY

    def __init__(
        self,
        coordinator: StationCoordinator,
        uid: str,
        evse: str | None,
        index: int,
        power_kw: float | None,
    ) -> None:
        super().__init__(coordinator, "charge_point")
        self._evse = evse
        self._index = index
        self._attr_unique_id = f"{coordinator.key}_point_{uid}"
        self._attr_name = point_name(index, power_kw)

    @property
    def _point(self) -> dict[str, Any] | None:
        points = (self.coordinator.view or {}).get("all_points", [])
        if self._evse:
            return next((p for p in points if p["evse"] == self._evse), None)
        return points[self._index - 1] if self._index <= len(points) else None

    @property
    def available(self) -> bool:
        return super().available and self._point is not None

    @property
    def is_on(self) -> bool | None:
        p = self._point
        if p is None or p["status"] not in ("occupied", "available"):
            return None  # unknown (also when out of service)
        return p["status"] == "occupied"

    @property
    def icon(self) -> str:
        if self.is_on is None:
            return "mdi:help-circle-outline"
        return "mdi:car-electric" if self.is_on else "mdi:ev-plug-type2"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        p = self._point
        if not p:
            return {}
        return {
            "status": p["status"],
            "status_raw": p["status_raw"],
            "evse_id": p["evse"],
            "connectors": p["connectors"],
            "power_kw": p["power_kw"],
            "cable_attached": p["cable_attached"],
            "within_filter": p["qualifies"],
        }
