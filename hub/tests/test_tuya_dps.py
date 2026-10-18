from __future__ import annotations

import pytest

from cordyhome.adapters.tuya.dps import DpMap, dp_map_from_strategy, parse_dps

STRATEGY = {
    1: {"status_code": "switch_1", "config_item": {"valueDesc": "{}"}},
    18: {
        "status_code": "cur_current",
        "config_item": {"valueDesc": '{"unit":"mA","min":0,"max":30000,"scale":0,"step":1}'},
    },
    19: {
        "status_code": "cur_power",
        "config_item": {"valueDesc": '{"unit":"W","min":0,"max":50000,"scale":1,"step":1}'},
    },
    20: {
        "status_code": "cur_voltage",
        "config_item": {"valueDesc": '{"unit":"V","min":0,"max":5000,"scale":1,"step":1}'},
    },
}


def test_strategy_builds_scaled_map():
    mapping = dp_map_from_strategy(STRATEGY)
    assert mapping is not None
    values = parse_dps({"1": True, "18": 812, "19": 1034, "20": 1271}, mapping)
    assert values["is_on"] is True
    assert values["power_w"] == pytest.approx(103.4)
    assert values["voltage_v"] == pytest.approx(127.1)
    assert values["current_a"] == pytest.approx(0.812)


def test_map_roundtrip_and_default():
    mapping = dp_map_from_strategy(STRATEGY)
    assert DpMap.from_dict(mapping.to_dict()) == mapping
    assert DpMap.from_dict(None).power.dp == 19


def test_plug_without_meter_has_no_energy_dps():
    mapping = dp_map_from_strategy({1: {"status_code": "switch_1", "config_item": {}}})
    assert mapping.power is None and mapping.energy_dps == []
    assert parse_dps({"1": False}, mapping) == {"is_on": False}


LIGHT_V2 = {
    20: {"status_code": "switch_led", "config_item": {"valueDesc": "{}"}},
    21: {"status_code": "work_mode", "config_item": {"valueDesc": "{}"}},
    22: {"status_code": "bright_value_v2", "config_item": {"valueDesc": '{"min":10,"max":1000}'}},
    23: {"status_code": "temp_value_v2", "config_item": {"valueDesc": '{"min":0,"max":1000}'}},
    24: {"status_code": "colour_data_v2", "config_item": {"valueDesc": "{}"}},
}


def test_light_v2_capabilities_state_and_commands():
    mapping = dp_map_from_strategy(LIGHT_V2)
    assert mapping.switch == 20
    assert mapping.capabilities == ["power", "brightness", "color_temp", "color"]
    assert DpMap.from_dict(mapping.to_dict()) == mapping

    values = parse_dps(
        {"20": True, "21": "colour", "22": 505, "23": 0, "24": "00f003e801f4"}, mapping
    )
    assert values["is_on"] is True
    assert values["state"] == {
        "mode": "colour",
        "brightness": 50,
        "color_temp": 0,
        "color": {"h": 240, "s": 100, "v": 50},
    }

    assert mapping.state_dps({"brightness": 100}) == {"20": True, "22": 1000, "21": "white"}
    assert mapping.state_dps({"color": {"h": 240, "s": 100, "v": 50}}) == {
        "20": True,
        "24": "00f003e801f4",
        "21": "colour",
    }


def test_legacy_light_uses_255_ranges_and_rgb_colour():
    mapping = dp_map_from_strategy(
        {
            1: {"status_code": "switch_led", "config_item": {}},
            3: {"status_code": "bright_value", "config_item": {}},
            5: {"status_code": "colour_data", "config_item": {}},
        }
    )
    assert (mapping.brightness.min, mapping.brightness.max) == (25, 255)
    assert mapping.colour.v2 is False
    encoded = mapping.state_dps({"color": {"h": 0, "s": 100, "v": 100}})["5"]
    assert encoded == "ff00000000ffff"
    assert parse_dps({"5": encoded}, mapping)["state"]["color"] == {"h": 0, "s": 100, "v": 100}
