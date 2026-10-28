from custom_components.enbw_charging_stations.parser import (
    build_view,
    clean_address,
    compress_opening_hours,
    normalize_plug,
    parse_ids,
    picture_kind,
    point_name,
    summarize,
    visual_state,
)

DETAIL = {
    "stationId": 123,
    "shortAddress": "Voorbeeldstad, Proefstraat 1",
    "lat": 52.37,
    "lon": 4.90,
    "plugTypeNames": ["CCS", "Type 2"],
    "openingTimes": {"twentyFourSeven": True},
    "chargePoints": [
        {"evseId": "A", "status": "AVAILABLE", "connectors": [{"plugTypeName": "CCS", "maxPowerInKw": 150}]},
        {"evseId": "B", "status": "OCCUPIED", "connectors": [{"plugTypeName": "CCS", "maxPowerInKw": 150}]},
        {"evseId": "C", "status": "AVAILABLE", "connectors": [{"plugTypeName": "Type 2", "maxPowerInKw": 22}]},
        {"evseId": "D", "status": "OUT_OF_SERVICE", "connectors": [{"plugTypeName": "Type 2", "maxPowerInKw": 22}]},
    ],
}


def test_view_counts_and_summary():
    v = build_view(DETAIL)
    assert (v["total"], v["free"], v["occupied"], v["broken"]) == (4, 2, 1, 1)
    assert summarize(v) == "2/4 available" and v["max_power_kw"] == 150 and v["open"] is True


def test_plug_and_power_filter():
    v = build_view(DETAIL, plugs=["CCS"])
    assert (v["total"], v["free"]) == (2, 1)
    v = build_view(DETAIL, min_power=100)
    assert (v["total"], v["free"]) == (2, 1)
    assert build_view(DETAIL, plugs=["Type 2"], min_power=50)["total"] == 0


def test_fallback_to_counts_without_points():
    v = build_view({"stationId": 1, "numberOfChargePoints": 3, "availableChargePoints": 2})
    assert (v["total"], v["free"], v["occupied"]) == (3, 2, 1)


def test_closed_station():
    v = build_view({**DETAIL, "openingTimes": {"nextOpeningTime": "2026-10-22T08:00:00Z"}})
    assert v["open"] is False and summarize(v) == "Closed"


def test_opening_hours_compress():
    s = "Mo: 08:00 - 20:00 Di: 08:00 - 20:00 Mi: 08:00 - 20:00 Do: 09:00 - 12:00"
    assert compress_opening_hours(s) == "Mon-Wed: 08:00 - 20:00, Thu: 09:00 - 12:00"  # German in, English out


def test_helpers():
    assert parse_ids("12, 34;12 56") == ["12", "34", "56"]


def test_typ_2_becomes_type_2():
    detail = {
        **DETAIL,
        "plugTypeNames": ["Typ 2", "CCS"],
        "chargePoints": [
            {"evseId": "A", "status": "AVAILABLE", "connectors": [{"plugTypeName": "Typ 2", "maxPowerInKw": 17}]}
        ],
    }
    assert normalize_plug("Typ 2") == "Type 2" and normalize_plug("Type 2") == "Type 2"
    assert build_view(detail)["plug_types"] == ["CCS", "Type 2"]
    assert build_view(detail, plugs=["Typ 2"])["total"] == 1  # an old saved filter keeps working
    assert build_view(detail)["points"][0]["connectors"] == ["Type 2"]


def test_visual_icons_per_point():
    assert visual_state(build_view(DETAIL)) == "🅿️/⛔/🅿️/⚫"
    one = {**DETAIL, "chargePoints": DETAIL["chargePoints"][:2]}  # 1 available, 1 occupied
    assert visual_state(build_view(one)) == "🅿️/⛔"
    busy = {**DETAIL, "chargePoints": [DETAIL["chargePoints"][1], DETAIL["chargePoints"][1]]}
    assert visual_state(build_view(busy)) == "⛔/⛔"
    closed = {**DETAIL, "openingTimes": {"nextOpeningTime": "x"}}
    assert visual_state(build_view(closed)) == "⛔/⛔/⛔/⛔"
    assert visual_state(build_view({**DETAIL, "chargePoints": DETAIL["chargePoints"][3:]})) == "⚫"
    assert visual_state(None) == "⚫"
    counts = build_view({"stationId": 1, "numberOfChargePoints": 3, "availableChargePoints": 2})
    assert visual_state(counts) == "🅿️/🅿️/⛔"


def test_picture_kind():
    assert (
        picture_kind(build_view({**DETAIL, "chargePoints": [DETAIL["chargePoints"][0], DETAIL["chargePoints"][2]]}))
        == "available_2"
    )
    assert picture_kind(build_view(DETAIL)) == "available_2"  # 2 of 4 free
    assert picture_kind(build_view({**DETAIL, "chargePoints": DETAIL["chargePoints"][:2]})) == "available"  # 1 free
    assert picture_kind(build_view({**DETAIL, "chargePoints": [DETAIL["chargePoints"][1]]})) == "unavailable"
    assert picture_kind(build_view({**DETAIL, "openingTimes": {"nextOpeningTime": "x"}})) == "unavailable"
    assert picture_kind(None) == "unknown"


def test_point_name_and_all_points():
    assert point_name(1, 17.0) == "Charge point 1 - 17kW" and point_name(2, None) == "Charge point 2"
    v = build_view(DETAIL, plugs=["CCS"])
    assert len(v["all_points"]) == 4 and len(v["points"]) == 2
    assert v["all_points"][0]["name"] == "Charge point 1 - 150kW" and v["all_points"][2]["number"] == 3


def test_clean_address_removes_postcode():
    assert clean_address("Voorbeeldlaan 14, 1234AB Voorbeeldstad, NL") == "Voorbeeldlaan 14, Voorbeeldstad, NL"
    assert clean_address("Teststraat 4 , 5678 CD Voorbeeldstad, NL") == "Teststraat 4, Voorbeeldstad, NL"
    assert clean_address("Ketelsteeg 14 , 5301KC Zaltbommel, NL") == "Ketelsteeg 14, Zaltbommel, NL"
    assert clean_address("Hauptstr. 12, 70173 Stuttgart, DE") == "Hauptstr. 12, Stuttgart, DE"
    assert clean_address("Voorbeeldstad, Proefstraat 1") == "Voorbeeldstad, Proefstraat 1"


def test_defect_statuses_count_as_out_of_service():
    from custom_components.enbw_charging_stations.parser import map_status

    for raw in ("INOPERATIVE", "faulted", "Out-of-Order", "BLOCKED", "UNAVAILABLE"):
        assert map_status(raw) == "out_of_service"
    assert map_status("CHARGING") == "occupied"
    assert map_status(None) == "unknown"


def test_picture_kind_unknown_when_stale():
    from custom_components.enbw_charging_stations.parser import picture_kind

    view = {"total": 2, "free": 2, "open": True}
    assert picture_kind(view) == "available_2"
    assert picture_kind(view, stale=True) == "unknown"


def test_street_and_number():
    from custom_components.enbw_charging_stations.parser import street_and_number

    assert street_and_number("Voorbeeldlaan 14, Voorbeeldstad, NL") == "Voorbeeldlaan 14"
    assert street_and_number("Voorbeeldstad, Proefstraat 1") == "Proefstraat 1"
    assert street_and_number("Alleen een naam") == "Alleen een naam"
    assert street_and_number(None) is None


def test_list_label_and_distance_format():
    from custom_components.enbw_charging_stations.parser import format_distance, list_label

    assert list_label("Hoofdlaan 1, Amsterdam, NL") == "Hoofdlaan 1, Amsterdam"
    assert list_label("Hoofdlaan 1, Amsterdam") == "Hoofdlaan 1, Amsterdam"
    assert format_distance(140.4) == "140m"
    assert format_distance(1234) == "1,2km"
