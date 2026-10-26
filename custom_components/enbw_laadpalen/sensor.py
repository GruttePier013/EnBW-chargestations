"""Sensors per charging station."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import MATCH_ALL, EntityCategory, UnitOfLength, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN, NAMES_NL
from .coordinator import EnbwConfigEntry, StationCoordinator
from .parser import summarize, visual_icons, visual_state


async def async_setup_entry(
    hass: HomeAssistant, entry: EnbwConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    entities: list[EnbwEntity] = []
    for c in entry.runtime_data.coordinators.values():
        entities += [
            Points(c),
            FreePoints(c),
            AvailabilityVisual(c),
            PlugTypes(c),
            MaxPower(c),
            NearbyPersons(c),
            NearestPersonDistance(c),
            FetchedCount(c),
            ErrorCount(c),
            LastUpdate(c),
            StationId(c),
        ]
        if c.station.get("distance_m") is not None:
            entities.append(StationDistance(c))
    async_add_entities(entities)


class EnbwEntity(CoordinatorEntity[StationCoordinator]):
    _attr_has_entity_name = True
    # State history is enough for these entities; keep the recorder database small.
    _unrecorded_attributes = frozenset({MATCH_ALL})

    def __init__(self, coordinator: StationCoordinator, key: str) -> None:
        super().__init__(coordinator)
        self._attr_translation_key = key  # for translated states (select options) and names
        if key in NAMES_NL:  # names (and entity ids) are fixed Dutch; the rest comes from translations
            self._attr_name = NAMES_NL[key]
        self._attr_unique_id = f"{coordinator.key}_{key}"
        loc = coordinator.location
        # 'Visit' on the device page opens the station on a map
        url = (
            f"https://www.openstreetmap.org/?mlat={loc[0]:.6f}&mlon={loc[1]:.6f}#map=18/{loc[0]:.6f}/{loc[1]:.6f}"
            if loc
            else "https://www.enbw.com/elektromobilitaet/unterwegs-laden#ladestations-finder"
        )
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.key)},
            name=coordinator.station["name"],
            manufacturer="EnBW",
            model="EnBW-laadpaal",
            configuration_url=url,
        )


class Points(EnbwEntity, SensorEntity):
    """State '2/4 beschikbaar' / 'Gesloten' + attribute ``charge_points`` with the status per charge point."""

    _attr_icon = "mdi:ev-station"

    def __init__(self, coordinator: StationCoordinator) -> None:
        super().__init__(coordinator, "points")

    @property
    def native_value(self) -> str | None:
        return summarize(self.coordinator.view) if self.coordinator.data else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        c = self.coordinator
        v = c.view
        if not v:
            return {}
        return {
            "updated": dt_util.as_local(c.data["fetched"]).replace(microsecond=0).isoformat(),
            "data_age_min": c.age_minutes(),
            "available": v["free"],
            "occupied": v["occupied"],
            "out_of_service": v["broken"],
            "unknown": v["unknown"],
            "total": v["total"],
            "open": v["open"],
            "opening_hours": v["opening_hours"],
            "closed_on_holidays": v["closed_on_holidays"],
            "next_opening": v["next_opening"],
            "next_closing": v["next_closing"],
            "address": v["address"],
            "charge_points": v["points"],
            "connector_filter": c.plugs,
            "min_power_kw": c.min_power,
        }


class FreePoints(EnbwEntity, SensorEntity):
    """Number of available charge points: 0, 1, 2 or more (for graphs and automations)."""

    _attr_icon = "mdi:ev-plug-type2"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: StationCoordinator) -> None:
        super().__init__(coordinator, "free_points")

    @property
    def native_value(self) -> int | None:
        v = self.coordinator.view
        return v["free"] if v else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        v = self.coordinator.view
        return {"total": v["total"], "occupied": v["occupied"]} if v else {}


class AvailabilityVisual(EnbwEntity, SensorEntity):
    """One icon per charge point, e.g. '🅿️/⛔': 🅿️ available, ⛔ occupied or closed, ⚫ something wrong."""

    _LEGEND = {
        "🅿️": "Charge point available",
        "⛔": "Charge point occupied (or station closed)",
        "⚫": "Something wrong: no data, out of service or unknown status",
    }

    def __init__(self, coordinator: StationCoordinator) -> None:
        super().__init__(coordinator, "availability_visual")

    @property
    def available(self) -> bool:
        return True  # on a failure we show ⚫ instead of 'unavailable'

    def _view(self):
        c = self.coordinator
        return c.fresh_view  # None (⚫) on errors or data older than a day

    @property
    def native_value(self) -> str:
        return visual_state(self._view())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        v = self._view()
        icons = visual_icons(v)
        names = [p["name"] for p in v["points"]] if v and v["points"] and v["open"] is not False else []
        per_point = [
            {"charge_point": names[i] if i < len(names) else f"Laadpunt {i + 1}", "icon": icon}
            for i, icon in enumerate(icons)
        ]
        return {"per_charge_point": per_point, "legend": self._LEGEND}


class PlugTypes(EnbwEntity, SensorEntity):
    """Connector types of the station: 'CCS, Type 2'."""

    _attr_icon = "mdi:ev-plug-ccs2"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: StationCoordinator) -> None:
        super().__init__(coordinator, "plug_types")

    @property
    def native_value(self) -> str | None:
        v = self.coordinator.view
        if v is None:
            return None
        return ", ".join(v["plug_types"]) or "Onbekend"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        v = self.coordinator.view
        return {"connector_types": v["plug_types"], "count": len(v["plug_types"])} if v else {}


class MaxPower(EnbwEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = UnitOfPower.KILO_WATT
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: StationCoordinator) -> None:
        super().__init__(coordinator, "max_power")

    @property
    def native_value(self) -> float | None:
        v = self.coordinator.view
        return v["max_power_kw"] if v else None


class NearbyPersons(EnbwEntity, SensorEntity):
    """'Geen' or the names of the tracked persons inside the zone radius of the station."""

    _attr_icon = "mdi:account-multiple"

    def __init__(self, coordinator: StationCoordinator) -> None:
        super().__init__(coordinator, "nearby_count")

    @property
    def available(self) -> bool:
        return True  # independent of whether EnBW answers

    def _names(self) -> list[str]:
        """Friendly names, closest first."""
        nearby = self.coordinator.nearby
        names = []
        for entity_id in sorted(nearby, key=lambda e: nearby[e]):
            state = self.hass.states.get(entity_id)
            names.append((state.attributes.get("friendly_name") if state else None) or entity_id)
        return names

    @property
    def native_value(self) -> str:
        return ", ".join(self._names()) or "Geen"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        c = self.coordinator
        return {
            "count": len(c.nearby),
            "persons": self._names(),
            "entities": sorted(c.nearby),
            "nearest_m": c.nearest_m,
            "radius_m": c.proximity_radius,
            "approaching": c.approaching,
        }


class NearestPersonDistance(EnbwEntity, SensorEntity):
    """Distance in meters from the station to the nearest tracked person (anywhere, not only in the zone)."""

    _attr_device_class = SensorDeviceClass.DISTANCE
    _attr_native_unit_of_measurement = UnitOfLength.METERS
    _attr_icon = "mdi:map-marker-distance"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: StationCoordinator) -> None:
        super().__init__(coordinator, "distance_to_person")

    @property
    def available(self) -> bool:
        return True  # independent of whether EnBW answers

    @property
    def native_value(self) -> int | None:
        return self.coordinator.nearest_m

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        c = self.coordinator
        entity_id = c.nearest_entity
        state = self.hass.states.get(entity_id) if entity_id else None
        return {
            "person": (state.attributes.get("friendly_name") if state else None) or entity_id,
            "entity_id": entity_id,
            "in_zone": bool(entity_id and entity_id in c.nearby),
            "approaching": c.approaching,
        }


class FetchedCount(EnbwEntity, SensorEntity):
    """Number of charge points the last API call returned (before the connector/power filter)."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:counter"

    def __init__(self, coordinator: StationCoordinator) -> None:
        super().__init__(coordinator, "fetched_points")

    @property
    def native_value(self) -> int | None:
        return self.coordinator.data["raw_points"] if self.coordinator.data else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        v = self.coordinator.view
        return {"after_filter": v["total"], "filter_active": v["filtered"]} if v else {}


class ErrorCount(EnbwEntity, SensorEntity):
    """Consecutive errors of this station; the station pauses automatic refreshes at the maximum."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False
    _attr_icon = "mdi:alert-circle-outline"

    def __init__(self, coordinator: StationCoordinator) -> None:
        super().__init__(coordinator, "error_count")

    @property
    def available(self) -> bool:
        return True

    @property
    def native_value(self) -> int:
        return self.coordinator.consecutive_errors

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        c = self.coordinator
        return {
            "paused": c.paused,
            "max_errors": c.max_errors,
            "api_consecutive_errors": c.api.consecutive_errors,
            "api_paused_for_s": round(c.api.blocked_for),
        }


class LastUpdate(EnbwEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: StationCoordinator) -> None:
        super().__init__(coordinator, "last_update")

    @property
    def native_value(self) -> datetime | None:
        return self.coordinator.data["fetched"] if self.coordinator.data else None


class _Metadata(EnbwEntity, SensorEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False


class StationId(_Metadata):
    """Location code (EnBW stationId) of the station, plus the EVSE ids of its charge points."""

    _attr_entity_registry_enabled_default = True
    _attr_icon = "mdi:barcode"

    def __init__(self, coordinator: StationCoordinator) -> None:
        super().__init__(coordinator, "station_id")

    @property
    def native_value(self) -> str:
        return self.coordinator.station_id

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        v = self.coordinator.view
        return {"evse_ids": [p["evse"] for p in v["all_points"] if p["evse"]]} if v else {}


class StationDistance(_Metadata):
    _attr_native_unit_of_measurement = UnitOfLength.METERS
    _attr_device_class = SensorDeviceClass.DISTANCE

    def __init__(self, coordinator: StationCoordinator) -> None:
        super().__init__(coordinator, "distance_m")

    @property
    def native_value(self) -> int | None:
        return self.coordinator.station.get("distance_m")
