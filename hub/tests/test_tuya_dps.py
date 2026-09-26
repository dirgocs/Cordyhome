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
