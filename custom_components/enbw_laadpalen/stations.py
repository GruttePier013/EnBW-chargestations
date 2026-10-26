"""Station configuration helpers (no Home Assistant imports)."""

from __future__ import annotations

from typing import Any

CONF_STATIONS = "stations"


def normalize_station(station: dict[str, Any]) -> dict[str, Any] | None:
    sid = station.get("id") or station.get("station_id")
    if sid in (None, ""):
        return None
    sid = str(sid)
    return {
        **station,
        "id": sid,
        "name": station.get("name") or f"Laadpaal {sid}",  # user-facing default name
        "plugs": [str(p) for p in (station.get("plugs") or [])],
        "min_power": float(station.get("min_power") or 0),
    }


def station_key(station: dict[str, Any]) -> str:
    """Stable id of a station = the EnBW stationId (also the device id)."""
    return station["id"]


def get_stations(entry: Any) -> list[dict[str, Any]]:
    raw = entry.options.get(CONF_STATIONS, entry.data.get(CONF_STATIONS, []))
    stations = [normalize_station(s) for s in raw if isinstance(s, dict)]
    return [s for s in stations if s]
