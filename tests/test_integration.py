"""Integration tests: setup, entities, flows, error protection, events (EnBW mocked)."""

import re

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.enbw_laadpalen.api import AddressNotFound
from custom_components.enbw_laadpalen.const import API_BASE, DOMAIN, PDOK_URL

from .test_parser import DETAIL

DEFAULTS = {
    "default_schedule": "never",
    "default_radius": 1000,
    "default_refresh_on_approach": True,
    "default_approach_only": True,
    "default_zone_interval": "every_5_min",
    "default_zone_stop_after": "30_min",
}
DETAIL_URL = f"{API_BASE}/chargestations/123"
LIST_RE = re.compile(rf"^{re.escape(API_BASE)}/chargestations\?")
STATION = {"id": "123", "name": "Proefstraat", "lat": 52.37, "lon": 4.90, "distance_m": 120}


def entry(**options):
    return MockConfigEntry(
        domain=DOMAIN, data={"api_key": "k", "stations": [STATION]}, options=options, unique_id=DOMAIN
    )


async def setup(hass, e):
    e.add_to_hass(hass)
    assert await hass.config_entries.async_setup(e.entry_id)
    await hass.async_block_till_done()


def eid(hass, platform, key):
    return er.async_get(hass).async_get_entity_id(platform, DOMAIN, f"123_{key}")


async def test_entities(hass: HomeAssistant, aioclient_mock):
    aioclient_mock.get(DETAIL_URL, json=DETAIL)
    await setup(hass, entry())
    st = hass.states.get(eid(hass, "sensor", "points"))
    assert st.state == "2/4 beschikbaar" and len(st.attributes["charge_points"]) == 4
    assert hass.states.get(eid(hass, "sensor", "free_points")).state == "2"
    assert hass.states.get(eid(hass, "sensor", "plug_types")).state == "CCS, Type 2"
    assert hass.states.get(eid(hass, "binary_sensor", "available")).state == "on"
    visual = hass.states.get(eid(hass, "sensor", "availability_visual"))
    assert visual.state == "🅿️/⛔/🅿️/⚫" and visual.attributes["per_charge_point"][1] == {
        "charge_point": "Laadpunt 2 - 150kW",
        "icon": "⛔",
    }
    assert hass.states.get(eid(hass, "sensor", "station_id")).state == "123"
    reg = er.async_get(hass)
    expected = {
        "A": ("off", "Laadpunt 1 - 150kW"),
        "B": ("on", "Laadpunt 2 - 150kW"),
        "C": ("off", "Laadpunt 3 - 22kW"),
        "D": ("unknown", "Laadpunt 4 - 22kW"),
    }
    for evse, (state, name) in expected.items():
        ent_id = reg.async_get_entity_id("binary_sensor", DOMAIN, f"123_point_{evse}")
        assert hass.states.get(ent_id).state == state
        assert hass.states.get(ent_id).attributes["friendly_name"].endswith(name)
    assert hass.states.get(eid(hass, "device_tracker", "location")).attributes["latitude"] == 52.37
    assert hass.states.get(eid(hass, "select", "refresh_schedule")).state == "never"
    assert aioclient_mock.call_count == 1  # only the first refresh


async def test_filter_and_refresh_button(hass: HomeAssistant, aioclient_mock):
    aioclient_mock.get(DETAIL_URL, json=DETAIL)
    e = MockConfigEntry(
        domain=DOMAIN, data={"api_key": "k", "stations": [{**STATION, "plugs": ["CCS"]}]}, unique_id=DOMAIN
    )
    await setup(hass, e)
    assert hass.states.get(eid(hass, "sensor", "points")).state == "1/2 beschikbaar"
    await hass.services.async_call("button", "press", {"entity_id": eid(hass, "button", "refresh")}, blocking=True)
    assert aioclient_mock.call_count == 2


async def test_unavailable_when_api_fails_and_recovers(hass: HomeAssistant, aioclient_mock):
    aioclient_mock.get(DETAIL_URL, status=500)
    await setup(hass, entry())
    assert hass.states.get(eid(hass, "sensor", "points")).state == "unavailable"
    aioclient_mock.clear_requests()
    aioclient_mock.get(DETAIL_URL, json=DETAIL)
    await hass.services.async_call("button", "press", {"entity_id": eid(hass, "button", "refresh")}, blocking=True)
    assert hass.states.get(eid(hass, "sensor", "points")).state == "2/4 beschikbaar"


async def test_auth_failure_starts_reauth(hass: HomeAssistant, aioclient_mock):
    aioclient_mock.get(DETAIL_URL, status=401)
    e = entry()
    await setup(hass, e)
    assert any(f["context"]["source"] == "reauth" for f in hass.config_entries.flow.async_progress())


async def test_nearby_person_names_and_binary_removed(hass: HomeAssistant, aioclient_mock):
    aioclient_mock.get(DETAIL_URL, json=DETAIL)
    reg = er.async_get(hass)
    e = entry()
    e.add_to_hass(hass)
    # old 'Persoon nabij' binary_sensor from an earlier version
    reg.async_get_or_create("binary_sensor", DOMAIN, "123_nearby", config_entry=e)
    assert await hass.config_entries.async_setup(e.entry_id)
    await hass.async_block_till_done()
    assert reg.async_get_entity_id("binary_sensor", DOMAIN, "123_nearby") is None
    assert hass.states.get(eid(hass, "sensor", "nearby_count")).state == "Geen"
    hass.states.async_set("person.alice", "home", {"latitude": 52.3701, "longitude": 4.9001, "friendly_name": "Alice"})
    hass.states.async_set("person.bob", "home", {"latitude": 52.3702, "longitude": 4.9002, "friendly_name": "Bob"})
    await hass.async_block_till_done()
    st = hass.states.get(eid(hass, "sensor", "nearby_count"))
    assert st.state == "Alice, Bob" and st.attributes["count"] == 2


async def test_title_renamed(hass: HomeAssistant, aioclient_mock):
    aioclient_mock.get(DETAIL_URL, json=DETAIL)
    e = MockConfigEntry(
        domain=DOMAIN, title="EnBW-laadpalen", data={"api_key": "k", "stations": [STATION]}, unique_id=DOMAIN
    )
    await setup(hass, e)
    assert e.title == "EnBW Laadpalen"


async def test_manual_flow_creates_entry(hass: HomeAssistant, aioclient_mock):
    aioclient_mock.get(LIST_RE, json=[])
    aioclient_mock.get(DETAIL_URL, json={**DETAIL, "shortAddress": "Voorbeeldstad, Proefstraat 1"})
    r = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert r["step_id"] == "user"
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {"api_key": "k"})
    assert r["step_id"] == "defaults"
    r = await hass.config_entries.flow.async_configure(r["flow_id"], DEFAULTS)
    assert r["type"] is FlowResultType.MENU
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {"next_step_id": "manual"})
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {"station_ids": "123"})
    assert r["step_id"] == "station_details"
    r = await hass.config_entries.flow.async_configure(
        r["flow_id"], {"name": "Mijn paal", "plug_types": ["CCS"], "min_power": 0}
    )
    assert r["type"] is FlowResultType.CREATE_ENTRY
    assert r["data"]["api_key"] == "k" and r["data"]["stations"][0]["id"] == "123"
    assert r["options"]["default_zone_interval"] == "every_5_min" and r["options"]["default_radius"] == 1000
    assert r["data"]["stations"][0]["plugs"] == ["CCS"]


async def test_invalid_key(hass: HomeAssistant, aioclient_mock):
    aioclient_mock.get(LIST_RE, status=401)
    r = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {"api_key": "bad"})
    assert r["errors"] == {"base": "invalid_auth"}


async def test_search_flow_and_options_remove(hass: HomeAssistant, aioclient_mock):
    listing = [
        {"stationId": 123, "lat": 52.3701, "lon": 4.9001, "shortAddress": "Voorbeeldstad, Proefstraat 1"},
        {"stationId": 999, "lat": 53.0, "lon": 6.0},
    ]
    aioclient_mock.get(LIST_RE, json=listing)
    aioclient_mock.get(DETAIL_URL, json=DETAIL)
    e = MockConfigEntry(domain=DOMAIN, data={"api_key": "k", "stations": []}, unique_id=DOMAIN)
    await setup(hass, e)
    r = await hass.config_entries.options.async_init(e.entry_id)
    r = await hass.config_entries.options.async_configure(r["flow_id"], {"next_step_id": "search"})
    r = await hass.config_entries.options.async_configure(
        r["flow_id"], {"location": {"latitude": 52.37, "longitude": 4.90, "radius": 250}}
    )
    assert r["step_id"] == "select_station_single"
    ph = r["description_placeholders"]
    assert (ph["count"], ph["total"]) == ("1", "344")  # 4 laadpunten: 150+150+22+22 kW
    assert ph["status_0"] == "2/4" and ph["details_0"] == "150kW 🗼, 123 📍, 13m ↗ NO"
    label = r["data_schema"].schema["station_0"].config["options"][0]["label"]
    assert label == "Voorbeeldstad, Proefstraat 1"  # row 1 = address; status and details are the helper text below it
    r = await hass.config_entries.options.async_configure(r["flow_id"], {"station_0": ["0"]})
    r = await hass.config_entries.options.async_configure(r["flow_id"], {"name": "Paal", "min_power": 0})
    assert r["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert [s["id"] for s in e.options["stations"]] == ["123"]
    assert eid(hass, "sensor", "points") is not None

    r = await hass.config_entries.options.async_init(e.entry_id)
    r = await hass.config_entries.options.async_configure(r["flow_id"], {"next_step_id": "remove_stations"})
    r = await hass.config_entries.options.async_configure(r["flow_id"], {"remove": ["123"]})
    await hass.async_block_till_done()
    assert e.options["stations"] == []


async def test_map_picture_follows_availability(hass: HomeAssistant, aioclient_mock):
    free_a, busy, free_c = DETAIL["chargePoints"][0], DETAIL["chargePoints"][1], DETAIL["chargePoints"][2]
    aioclient_mock.get(DETAIL_URL, json={**DETAIL, "chargePoints": [free_a, free_c]})
    await setup(hass, entry())
    ent = eid(hass, "device_tracker", "location")
    base = "/enbw_laadpalen/static/"
    assert hass.states.get(ent).attributes["entity_picture"] == base + "station_available.png"
    for points, expected in (([free_a, busy], "station_partial.png"), ([busy], "station_unavailable.png")):
        aioclient_mock.clear_requests()
        aioclient_mock.get(DETAIL_URL, json={**DETAIL, "chargePoints": points})
        await hass.services.async_call("button", "press", {"entity_id": eid(hass, "button", "refresh")}, blocking=True)
        assert hass.states.get(ent).attributes["entity_picture"] == base + expected


def test_brand_and_static_files_exist():
    from pathlib import Path

    base = Path(__file__).parent.parent / "custom_components" / DOMAIN
    for f in (
        "brand/icon.png",
        "brand/icon@2x.png",
        "brand/logo.png",
        "static/station_available.png",
        "static/station_partial.png",
        "static/station_unavailable.png",
    ):
        assert (base / f).is_file(), f


async def _zone_setup(hass, aioclient_mock, monkeypatch, approach_only=False):
    from custom_components.enbw_laadpalen import coordinator as coord_mod

    monkeypatch.setattr(coord_mod, "MIN_APPROACH_REFRESH_GAP", 0)
    aioclient_mock.get(DETAIL_URL, json=DETAIL)
    await setup(hass, entry())
    if not approach_only:
        await hass.services.async_call(
            "switch", "turn_off", {"entity_id": eid(hass, "switch", "approach_only")}, blocking=True
        )


def _person(hass, near: bool):
    pos = {"latitude": 52.3701, "longitude": 4.9001} if near else {"latitude": 53.0, "longitude": 6.0}
    hass.states.async_set("person.alice", "home" if near else "not_home", pos)


async def _advance(hass, freezer, minutes: float):
    from datetime import timedelta

    from pytest_homeassistant_custom_component.common import async_fire_time_changed

    freezer.tick(timedelta(minutes=minutes))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


async def test_zone_defaults(hass: HomeAssistant, aioclient_mock, monkeypatch):
    await _zone_setup(hass, aioclient_mock, monkeypatch, approach_only=True)
    assert hass.states.get(eid(hass, "select", "zone_refresh")).state == "every_5_min"
    assert hass.states.get(eid(hass, "select", "zone_stop_after")).state == "30_min"
    assert hass.states.get(eid(hass, "number", "proximity_radius")).state == "1000"
    assert hass.states.get(eid(hass, "switch", "approach_only")).state == "on"


async def test_zone_visit_window(hass: HomeAssistant, aioclient_mock, monkeypatch, freezer):
    await _zone_setup(hass, aioclient_mock, monkeypatch)
    await _advance(hass, freezer, 6)
    assert aioclient_mock.call_count == 1  # nobody in the zone: nothing
    _person(hass, True)
    await hass.async_block_till_done()
    assert aioclient_mock.call_count == 2  # binnenkomst: 1x
    for expected in (3, 4):
        await _advance(hass, freezer, 5)
        assert aioclient_mock.call_count == expected  # every 5 min
    # refreshing stops after 30 min, even though the person stays in the zone
    for _ in range(5):
        await _advance(hass, freezer, 5)
    count = aioclient_mock.call_count
    await _advance(hass, freezer, 5)
    await _advance(hass, freezer, 20)
    assert aioclient_mock.call_count == count
    assert 5 <= count - 2 <= 6


async def test_zone_cooldown_prevents_new_visit(hass: HomeAssistant, aioclient_mock, monkeypatch, freezer):
    await _zone_setup(hass, aioclient_mock, monkeypatch)
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": eid(hass, "select", "zone_refresh"), "option": "on_entry"},
        blocking=True,
    )
    _person(hass, True)
    await hass.async_block_till_done()
    assert aioclient_mock.call_count == 2  # nieuw bezoek
    _person(hass, False)
    await _advance(hass, freezer, 5)
    _person(hass, True)  # back within the cooldown (15 min): same visit, no refresh
    await hass.async_block_till_done()
    assert aioclient_mock.call_count == 2
    _person(hass, False)
    await _advance(hass, freezer, 20)  # longer than the cooldown: the visit is over
    _person(hass, True)
    await hass.async_block_till_done()
    assert aioclient_mock.call_count == 3  # nieuw bezoek


async def test_zone_switch_off_stops_everything(hass: HomeAssistant, aioclient_mock, monkeypatch, freezer):
    await _zone_setup(hass, aioclient_mock, monkeypatch)
    switch_id = eid(hass, "switch", "refresh_on_approach")
    await hass.services.async_call("switch", "turn_off", {"entity_id": switch_id}, blocking=True)
    _person(hass, True)
    await hass.async_block_till_done()
    await _advance(hass, freezer, 6)
    assert aioclient_mock.call_count == 1  # hoofdschakelaar uit
    await hass.services.async_call("switch", "turn_on", {"entity_id": switch_id}, blocking=True)
    await _advance(hass, freezer, 6)
    assert aioclient_mock.call_count == 2  # switched on while someone is in the zone: a visit starts, the interval runs


def _settings_input(**over):
    defaults = {**DEFAULTS, "apply_existing": False, **over.pop("defaults", {})}
    protection = {"max_errors": 5, "api_max_errors": 10, "api_spacing": 3, **over.pop("protection", {})}
    return {
        "persons": [],
        "zone_cooldown": 15,
        "defaults": defaults,
        "protection": protection,
        "api": {"api_key": over.pop("api_key", "k")},
        **over,
    }


async def _open_settings(hass, e):
    r = await hass.config_entries.options.async_init(e.entry_id)
    return await hass.config_entries.options.async_configure(r["flow_id"], {"next_step_id": "settings"})


async def test_settings_zone_cooldown_saved(hass: HomeAssistant, aioclient_mock):
    aioclient_mock.get(DETAIL_URL, json=DETAIL)
    e = entry()
    await setup(hass, e)
    r = await _open_settings(hass, e)
    assert r["step_id"] == "settings"
    r = await hass.config_entries.options.async_configure(r["flow_id"], _settings_input(zone_cooldown=30))
    assert r["type"] is FlowResultType.CREATE_ENTRY and e.options["zone_cooldown"] == 30
    assert e.options["default_zone_stop_after"] == "30_min"
    assert (e.options["max_errors"], e.options["api_max_errors"], e.options["api_spacing"]) == (5, 10, 3)


async def test_options_menu_has_no_api_key_entry(hass: HomeAssistant, aioclient_mock):
    aioclient_mock.get(DETAIL_URL, json=DETAIL)
    e = entry()
    await setup(hass, e)
    r = await hass.config_entries.options.async_init(e.entry_id)
    assert "api_key" not in r["menu_options"] and "settings" in r["menu_options"]


async def test_new_entities_start_with_defaults(hass: HomeAssistant, aioclient_mock):
    aioclient_mock.get(DETAIL_URL, json=DETAIL)
    await setup(
        hass,
        entry(
            default_schedule="hourly",
            default_radius=500,
            default_refresh_on_approach=False,
            default_approach_only=False,
            default_zone_interval="every_10_min",
            default_zone_stop_after="60_min",
        ),
    )
    assert hass.states.get(eid(hass, "select", "refresh_schedule")).state == "hourly"
    assert hass.states.get(eid(hass, "number", "proximity_radius")).state == "500"
    assert hass.states.get(eid(hass, "switch", "refresh_on_approach")).state == "off"
    assert hass.states.get(eid(hass, "switch", "approach_only")).state == "off"
    assert hass.states.get(eid(hass, "select", "zone_refresh")).state == "every_10_min"
    assert hass.states.get(eid(hass, "select", "zone_stop_after")).state == "60_min"


async def test_settings_apply_to_existing_only_when_ticked(hass: HomeAssistant, aioclient_mock):
    aioclient_mock.get(DETAIL_URL, json=DETAIL)
    e = entry()
    await setup(hass, e)
    sel = eid(hass, "select", "zone_refresh")
    await hass.services.async_call(
        "select", "select_option", {"entity_id": sel, "option": "every_15_min"}, blocking=True
    )
    new = {
        "default_zone_interval": "every_2_min",
        "default_radius": 2000,
        "default_refresh_on_approach": False,
        "default_approach_only": False,
    }
    # checkbox off: only the defaults are saved, existing stations keep their choice
    r = await _open_settings(hass, e)
    await hass.config_entries.options.async_configure(r["flow_id"], _settings_input(defaults=new))
    await hass.async_block_till_done()
    assert e.options["default_zone_interval"] == "every_2_min"
    assert hass.states.get(eid(hass, "select", "zone_refresh")).state == "every_15_min"
    assert hass.states.get(eid(hass, "number", "proximity_radius")).state != "2000"
    # checkbox on: existing stations get the defaults too
    r = await _open_settings(hass, e)
    await hass.config_entries.options.async_configure(
        r["flow_id"], _settings_input(defaults={**new, "apply_existing": True})
    )
    await hass.async_block_till_done()
    assert hass.states.get(eid(hass, "select", "zone_refresh")).state == "every_2_min"
    assert hass.states.get(eid(hass, "number", "proximity_radius")).state == "2000"
    assert hass.states.get(eid(hass, "switch", "refresh_on_approach")).state == "off"
    assert hass.states.get(eid(hass, "switch", "approach_only")).state == "off"


async def test_settings_api_key_change(hass: HomeAssistant, aioclient_mock):
    aioclient_mock.get(DETAIL_URL, json=DETAIL)
    e = entry()
    await setup(hass, e)
    aioclient_mock.get(LIST_RE, status=401)
    r = await _open_settings(hass, e)
    r = await hass.config_entries.options.async_configure(r["flow_id"], _settings_input(api_key="bad"))
    assert r["type"] is FlowResultType.FORM and r["errors"] == {"base": "invalid_auth"}
    aioclient_mock.clear_requests()
    aioclient_mock.get(LIST_RE, json=[])
    aioclient_mock.get(DETAIL_URL, json=DETAIL)
    r = await hass.config_entries.options.async_configure(r["flow_id"], _settings_input(api_key="nieuw"))
    assert r["type"] is FlowResultType.CREATE_ENTRY and e.data["api_key"] == "nieuw"


def test_translation_placeholders_match():
    import json
    import re
    from pathlib import Path

    base = Path(__file__).parent.parent / "custom_components" / DOMAIN / "translations"
    nl, en = (json.loads((base / f"{x}.json").read_text()) for x in ("nl", "en"))

    def walk(a, b, path=""):
        if isinstance(a, dict):
            assert set(a) == set(b), path
            for k in a:
                walk(a[k], b[k], f"{path}.{k}")
        elif isinstance(a, str):
            assert set(re.findall(r"\{(\w+)\}", a)) == set(re.findall(r"\{(\w+)\}", b)), path

    walk(nl, en)  # HA falls back to English when placeholders differ


async def test_select_plural_step_and_total_power(hass: HomeAssistant, aioclient_mock):
    aioclient_mock.get(
        LIST_RE,
        json=[{"stationId": 123, "lat": 52.3701, "lon": 4.9001}, {"stationId": 124, "lat": 52.3702, "lon": 4.9002}],
    )
    aioclient_mock.get(DETAIL_URL, json=DETAIL)
    aioclient_mock.get(
        f"{API_BASE}/chargestations/124", json={**DETAIL, "stationId": 124, "chargePoints": DETAIL["chargePoints"][:1]}
    )
    r = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {"api_key": "k"})
    r = await hass.config_entries.flow.async_configure(r["flow_id"], DEFAULTS)
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {"next_step_id": "search"})
    r = await hass.config_entries.flow.async_configure(
        r["flow_id"], {"location": {"latitude": 52.37, "longitude": 4.90, "radius": 250}}
    )
    assert r["step_id"] == "select_station"  # meervoud: '2 Laadpalen gevonden.'
    ph = r["description_placeholders"]
    assert (ph["count"], ph["total"]) == ("2", "494")  # 344 + 150 kW
    assert set(r["data_schema"].schema) == {"station_0", "station_1"} and "details_1" in ph


async def test_zone_place_name_moves_pin_then_search(hass: HomeAssistant, aioclient_mock):
    aioclient_mock.get(
        PDOK_URL,
        json={
            "response": {
                "docs": [
                    {
                        "weergavenaam": "Utrecht, Gelderland",
                        "centroide_ll": "POINT(4.9000 52.3233)",
                        "type": "woonplaats",
                    }
                ]
            }
        },
    )
    aioclient_mock.get(LIST_RE, json=[{"stationId": 123, "lat": 52.3233, "lon": 4.9000}])
    aioclient_mock.get(DETAIL_URL, json=DETAIL)
    r = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {"api_key": "k"})
    r = await hass.config_entries.flow.async_configure(r["flow_id"], DEFAULTS)
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {"next_step_id": "search"})
    assert list(r["data_schema"].schema)[0] == "address"  # the place name field is above the map
    home = {"latitude": hass.config.latitude, "longitude": hass.config.longitude, "radius": 250}
    # new place name -> the form reopens with pin, fields and place name at that place
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {"address": "Utrecht", "location": home})
    assert r["type"] is FlowResultType.FORM and r["step_id"] == "search"
    sug = {str(k): k.description["suggested_value"] for k in r["data_schema"].schema if k.description}
    assert sug["location"]["latitude"] == 52.3233 and sug["address"] == "Utrecht, Gelderland"
    assert set(r["data_schema"].schema) == {"address", "location"}  # one pair of GPS fields: the map selector's own
    # pin verfijnd/bevestigd, plaatsnaam ongewijzigd -> nu pas zoeken
    r = await hass.config_entries.flow.async_configure(
        r["flow_id"],
        {"address": "Utrecht, Gelderland", "location": {"latitude": 52.3233, "longitude": 4.9000, "radius": 250}},
    )
    assert r["step_id"] == "select_station_single"


async def test_zone_unknown_place_shows_error(hass: HomeAssistant, aioclient_mock):
    aioclient_mock.get(PDOK_URL, json={"response": {"docs": []}})
    aioclient_mock.get(LIST_RE, json=[])
    r = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {"api_key": "k"})
    r = await hass.config_entries.flow.async_configure(r["flow_id"], DEFAULTS)
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {"next_step_id": "search"})
    home = {"latitude": hass.config.latitude, "longitude": hass.config.longitude, "radius": 250}
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {"address": "Nergensdorp", "location": home})
    assert r["errors"] == {"base": "address_not_found"}


async def test_geocode_prefers_woonplaats_for_plain_place_names(hass: HomeAssistant, aioclient_mock):
    from homeassistant.helpers.aiohttp_client import async_get_clientsession

    from custom_components.enbw_laadpalen.api import EnbwApi

    docs = {
        "response": {
            "docs": [
                {"weergavenaam": "Amersfoort, Gelderland", "centroide_ll": "POINT(4.90 52.37)", "type": "woonplaats"}
            ]
        }
    }
    aioclient_mock.get(PDOK_URL, json=docs)
    api = EnbwApi(async_get_clientsession(hass), "k")
    assert await api.async_geocode("Amersfoort") == (52.37, 4.90, "Amersfoort, Gelderland")
    assert aioclient_mock.mock_calls[0][1].query["fq"] == "type:woonplaats"
    await api.async_geocode("Voorbeeldlaan 1, Voorbeeldstad")  # with house number/comma: all types
    assert "fq" not in aioclient_mock.mock_calls[1][1].query


async def test_geocode_falls_back_to_any_type(hass: HomeAssistant, aioclient_mock):
    from homeassistant.helpers.aiohttp_client import async_get_clientsession

    from custom_components.enbw_laadpalen.api import EnbwApi

    aioclient_mock.get(PDOK_URL, json={"response": {"docs": []}})
    with pytest.raises(AddressNotFound):
        await EnbwApi(async_get_clientsession(hass), "k").async_geocode("Nergensdorp")
    assert len(aioclient_mock.mock_calls) == 2  # first populated places, then all types


async def test_default_device_name_has_no_postcode(hass: HomeAssistant, aioclient_mock):
    aioclient_mock.get(LIST_RE, json=[])
    aioclient_mock.get(DETAIL_URL, json={**DETAIL, "shortAddress": "Voorbeeldlaan 14, 1234AB Voorbeeldstad, NL"})
    r = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {"api_key": "k"})
    r = await hass.config_entries.flow.async_configure(r["flow_id"], DEFAULTS)
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {"next_step_id": "manual"})
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {"station_ids": "123"})
    name_key = next(k for k in r["data_schema"].schema if k == "name")
    assert name_key.default() == "Voorbeeldlaan 14, Voorbeeldstad, NL"


# ---------------------------------------------------------------- error protection and API behaviour
async def test_api_spaces_automatic_calls(hass: HomeAssistant, aioclient_mock):
    import asyncio
    import time

    from homeassistant.helpers.aiohttp_client import async_get_clientsession

    from custom_components.enbw_laadpalen.api import EnbwApi

    aioclient_mock.get(DETAIL_URL, json=DETAIL)
    api = EnbwApi(async_get_clientsession(hass), "k", spacing=0.05)
    started = time.monotonic()
    await asyncio.gather(*(api.async_detail("123", auto=True) for _ in range(4)))
    assert time.monotonic() - started >= 0.14  # three gaps of 0.05 s, even though all started at once
    started = time.monotonic()
    await asyncio.gather(*(api.async_detail("123") for _ in range(4)))  # manual / config flow: not paced
    assert time.monotonic() - started < 0.1


async def test_api_circuit_breaker_and_manual_bypass(hass: HomeAssistant, aioclient_mock):
    from homeassistant.helpers.aiohttp_client import async_get_clientsession

    from custom_components.enbw_laadpalen.api import EnbwApi, EnbwApiError, EnbwBlocked

    aioclient_mock.get(DETAIL_URL, status=500)
    api = EnbwApi(async_get_clientsession(hass), "k", max_errors=3)
    changes: list[bool] = []
    api.on_outage_change = changes.append
    for _ in range(3):
        with pytest.raises(EnbwApiError):
            await api.async_detail("123", auto=True)
    assert api.outage and changes == [True]
    calls = aioclient_mock.call_count
    with pytest.raises(EnbwBlocked):
        await api.async_detail("123", auto=True)  # paused: no request is made
    assert aioclient_mock.call_count == calls
    aioclient_mock.clear_requests()
    aioclient_mock.get(DETAIL_URL, json=DETAIL)
    await api.async_detail("123")  # manual call bypasses the pause; success resets the breaker
    assert not api.outage and changes == [True, False] and api.consecutive_errors == 0


async def test_api_rate_limit_uses_retry_after(hass: HomeAssistant, aioclient_mock):
    from homeassistant.helpers.aiohttp_client import async_get_clientsession

    from custom_components.enbw_laadpalen.api import EnbwApi, EnbwApiError

    aioclient_mock.get(DETAIL_URL, status=429, headers={"Retry-After": "120"})
    api = EnbwApi(async_get_clientsession(hass), "k", max_errors=10)
    with pytest.raises(EnbwApiError):
        await api.async_detail("123", auto=True)
    assert api.outage and 100 < api.blocked_for <= 120


async def test_api_outage_creates_and_clears_repair_issue(hass: HomeAssistant, aioclient_mock):
    from homeassistant.helpers import issue_registry as ir

    aioclient_mock.get(DETAIL_URL, json=DETAIL)
    e = entry()
    await setup(hass, e)
    api = e.runtime_data.api
    api._record_failure(retry_after=120)
    assert ir.async_get(hass).async_get_issue(DOMAIN, "api_paused") is not None
    api._record_success()
    assert ir.async_get(hass).async_get_issue(DOMAIN, "api_paused") is None


async def test_station_pauses_after_errors_and_resumes_manually(hass: HomeAssistant, aioclient_mock):
    from homeassistant.helpers import issue_registry as ir

    aioclient_mock.get(DETAIL_URL, json=DETAIL)
    e = entry(max_errors=2)
    await setup(hass, e)
    coordinator = e.runtime_data.coordinators["123"]
    aioclient_mock.clear_requests()
    aioclient_mock.get(DETAIL_URL, status=500)
    await coordinator.async_manual_refresh()
    assert not coordinator.paused and coordinator.consecutive_errors == 1
    await coordinator.async_manual_refresh()
    assert coordinator.paused
    assert ir.async_get(hass).async_get_issue(DOMAIN, "station_paused_123") is not None
    assert hass.states.get(eid(hass, "binary_sensor", "paused")).state == "on"
    calls = aioclient_mock.call_count
    await coordinator.async_auto_refresh()  # automatic refreshes are skipped while paused
    assert aioclient_mock.call_count == calls
    aioclient_mock.clear_requests()
    aioclient_mock.get(DETAIL_URL, json=DETAIL)
    await coordinator.async_manual_refresh()  # a manual refresh works and resumes the station
    assert not coordinator.paused and coordinator.consecutive_errors == 0
    assert ir.async_get(hass).async_get_issue(DOMAIN, "station_paused_123") is None
    assert hass.states.get(eid(hass, "binary_sensor", "paused")).state == "off"


async def test_station_backs_off_after_an_error(hass: HomeAssistant, aioclient_mock):
    aioclient_mock.get(DETAIL_URL, json=DETAIL)
    e = entry()
    await setup(hass, e)
    coordinator = e.runtime_data.coordinators["123"]
    aioclient_mock.clear_requests()
    aioclient_mock.get(DETAIL_URL, status=500)
    await coordinator.async_manual_refresh()
    calls = aioclient_mock.call_count
    await coordinator.async_auto_refresh()  # still inside the backoff window
    assert aioclient_mock.call_count == calls


async def test_api_paused_skips_automatic_refresh(hass: HomeAssistant, aioclient_mock):
    aioclient_mock.get(DETAIL_URL, json=DETAIL)
    e = entry()
    await setup(hass, e)
    coordinator = e.runtime_data.coordinators["123"]
    e.runtime_data.api._record_failure(retry_after=300)
    calls = aioclient_mock.call_count
    await coordinator.async_auto_refresh()
    assert aioclient_mock.call_count == calls
    assert hass.states.get(eid(hass, "sensor", "points")).state == "2/4 beschikbaar"  # keeps the last data


# ---------------------------------------------------------------- event: charge point freed
async def test_freed_charge_point_fires_event_only_with_people_in_zone(hass: HomeAssistant, aioclient_mock):
    from pytest_homeassistant_custom_component.common import async_capture_events

    from custom_components.enbw_laadpalen.const import EVENT_CHARGE_POINT_AVAILABLE

    aioclient_mock.get(DETAIL_URL, json=DETAIL)
    await setup(hass, entry())
    events = async_capture_events(hass, EVENT_CHARGE_POINT_AVAILABLE)
    points = DETAIL["chargePoints"]
    freed = {**DETAIL, "chargePoints": [points[0], {**points[1], "status": "AVAILABLE"}, *points[2:]]}
    press = {"entity_id": eid(hass, "button", "refresh")}

    aioclient_mock.clear_requests()
    aioclient_mock.get(DETAIL_URL, json=freed)  # occupied -> available, but nobody is nearby
    await hass.services.async_call("button", "press", press, blocking=True)
    assert events == []

    aioclient_mock.clear_requests()
    aioclient_mock.get(DETAIL_URL, json=DETAIL)  # occupied again
    await hass.services.async_call("button", "press", press, blocking=True)
    hass.states.async_set("person.alice", "home", {"latitude": 52.3701, "longitude": 4.9001, "friendly_name": "Alice"})
    await hass.async_block_till_done()
    aioclient_mock.clear_requests()
    aioclient_mock.get(DETAIL_URL, json=freed)
    await hass.services.async_call("button", "press", press, blocking=True)
    await hass.async_block_till_done()
    assert len(events) == 1
    data = events[0].data
    assert data["station_id"] == "123" and data["charge_point"] == "Laadpunt 2 - 150kW"
    assert data["persons"] == ["Alice"] and data["available"] == 3 and data["total"] == 4
    assert (
        hass.states.get(eid(hass, "event", "charge_point_event")).attributes["event_type"] == "charge_point_available"
    )


# ---------------------------------------------------------------- distance to nearest person and approach-only
async def test_nearest_person_distance_sensor(hass: HomeAssistant, aioclient_mock):
    aioclient_mock.get(DETAIL_URL, json=DETAIL)
    await setup(hass, entry())
    sensor = eid(hass, "sensor", "nearest_person_distance")
    assert hass.states.get(sensor).state == "unknown"
    hass.states.async_set("person.alice", "not_home", {"latitude": 53.0, "longitude": 6.0, "friendly_name": "Alice"})
    await hass.async_block_till_done()
    st = hass.states.get(sensor)
    assert int(st.state) % 1000 == 0 and int(st.state) > 50_000  # far away: rounded to whole kilometers
    assert st.attributes["person"] == "Alice" and st.attributes["in_zone"] is False
    hass.states.async_set("person.alice", "home", {"latitude": 52.3701, "longitude": 4.9001, "friendly_name": "Alice"})
    await hass.async_block_till_done()
    st = hass.states.get(sensor)
    assert st.state == "10" and st.attributes["in_zone"] is True  # 13 m, rounded to 10 m


async def test_zone_refresh_only_while_approaching(hass: HomeAssistant, aioclient_mock, monkeypatch, freezer):
    await _zone_setup(hass, aioclient_mock, monkeypatch, approach_only=True)

    def at(lat: float):
        hass.states.async_set("person.alice", "not_home", {"latitude": lat, "longitude": 4.90})

    at(52.3772)  # about 800 m away, inside the 1000 m zone
    await hass.async_block_till_done()
    assert aioclient_mock.call_count == 2  # entry refresh
    await _advance(hass, freezer, 5)
    assert aioclient_mock.call_count == 2  # standing still: no refresh
    at(52.3750)  # about 555 m: getting closer
    await hass.async_block_till_done()
    await _advance(hass, freezer, 6)
    assert aioclient_mock.call_count == 3  # approaching since the last tick: the interval refresh happens
    await _advance(hass, freezer, 5)
    assert aioclient_mock.call_count == 3  # not getting closer any more: no refresh
    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": eid(hass, "switch", "approach_only")}, blocking=True
    )
    await _advance(hass, freezer, 5)
    assert aioclient_mock.call_count == 4  # approach-only off: refreshes as long as someone is in the zone


# ---------------------------------------------------------------- diagnostics
async def test_diagnostics_redacts_key_and_includes_raw_response(hass: HomeAssistant, aioclient_mock):
    from homeassistant.helpers import device_registry as dr

    from custom_components.enbw_laadpalen.diagnostics import (
        async_get_config_entry_diagnostics,
        async_get_device_diagnostics,
    )

    aioclient_mock.get(DETAIL_URL, json=DETAIL)
    e = entry()
    await setup(hass, e)
    diag = await async_get_config_entry_diagnostics(hass, e)
    assert diag["entry"]["data"]["api_key"] == "**REDACTED**"
    station = diag["stations"]["123"]
    assert station["raw_response"]["stationId"] == 123 and station["health"]["paused"] is False
    assert station["settings"]["zone_interval_min"] == 5 and "api" in diag
    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, "123")})
    assert (await async_get_device_diagnostics(hass, e, device))["raw_response"]["stationId"] == 123


async def test_tracker_state_shows_availability(hass: HomeAssistant, aioclient_mock):
    aioclient_mock.get(DETAIL_URL, json=DETAIL)
    await setup(hass, entry())
    state = hass.states.get(eid(hass, "device_tracker", "location"))
    assert state.state == "2/4 beschikbaar"  # same text as the 'Laadpunten' sensor, not 'not_home'
    assert state.attributes["visual"] == "🅿️/⛔/🅿️/⚫" and state.attributes["available"] == 2
    assert state.attributes["latitude"] == 52.37  # still a working map marker
    aioclient_mock.clear_requests()
    aioclient_mock.get(DETAIL_URL, status=500)
    await hass.services.async_call("button", "press", {"entity_id": eid(hass, "button", "refresh")}, blocking=True)
    assert hass.states.get(eid(hass, "device_tracker", "location")).state == "Onbekend"


async def test_backoff_does_not_clash_with_coordinator_base_class(hass: HomeAssistant, aioclient_mock):
    """Regression: our backoff once reused the base class attribute `_retry_after` (reset to None in its __init__)."""
    aioclient_mock.get(DETAIL_URL, json=DETAIL)
    e = entry()
    await setup(hass, e)
    coordinator = e.runtime_data.coordinators["123"]
    assert isinstance(coordinator._backoff_until, float)
    aioclient_mock.clear_requests()
    aioclient_mock.get(DETAIL_URL, status=500)
    await coordinator.async_manual_refresh()
    assert coordinator._backoff_until > 0
    assert coordinator._retry_after is None  # the base class attribute is left alone
    await coordinator.async_auto_refresh()  # must not raise a TypeError while backing off


async def test_unload_removes_station_repair_issue(hass: HomeAssistant, aioclient_mock):
    from homeassistant.helpers import issue_registry as ir

    aioclient_mock.get(DETAIL_URL, json=DETAIL)
    e = entry(max_errors=1)
    await setup(hass, e)
    aioclient_mock.clear_requests()
    aioclient_mock.get(DETAIL_URL, status=500)
    await e.runtime_data.coordinators["123"].async_manual_refresh()
    assert ir.async_get(hass).async_get_issue(DOMAIN, "station_paused_123") is not None
    assert await hass.config_entries.async_unload(e.entry_id)
    assert ir.async_get(hass).async_get_issue(DOMAIN, "station_paused_123") is None


async def test_startup_refresh_is_limited_to_five_concurrent_calls(hass: HomeAssistant, aioclient_mock):
    import asyncio

    active = peak = 0

    async def slow(method, url, data):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.01)
        active -= 1
        from tests.test_integration import DETAIL as detail  # noqa: PLC0415

        return AiohttpClientMockResponse(method, url, json=detail)

    from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMockResponse

    for sid in range(1, 13):
        aioclient_mock.get(f"{API_BASE}/chargestations/{sid}", side_effect=slow)
    stations = [{**STATION, "id": str(i), "name": f"Paal {i}"} for i in range(1, 13)]
    e = MockConfigEntry(domain=DOMAIN, data={"api_key": "k", "stations": stations}, unique_id=DOMAIN)
    await setup(hass, e)
    assert 1 < peak <= 5


async def test_refresh_all_service_and_stale_data(hass: HomeAssistant, aioclient_mock):
    from datetime import timedelta

    from homeassistant.util import dt as dt_util

    aioclient_mock.get(DETAIL_URL, json=DETAIL)
    e = entry()
    await setup(hass, e)
    assert hass.services.has_service(DOMAIN, "refresh_all")
    before = len(aioclient_mock.mock_calls)
    await hass.services.async_call(DOMAIN, "refresh_all", {}, blocking=True)
    assert len(aioclient_mock.mock_calls) > before

    coordinator = e.runtime_data.coordinators["123"]
    assert not coordinator.is_stale and coordinator.fresh_view
    coordinator.data["fetched"] = dt_util.utcnow() - timedelta(days=2)
    assert coordinator.is_stale and coordinator.fresh_view is None
