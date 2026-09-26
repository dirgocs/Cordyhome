from __future__ import annotations

import pytest

from cordyhome.db import Database
from cordyhome.services.energy import EnergyMeter, energy_report
from tests.conftest import START


@pytest.fixture
def db():
    database = Database(":memory:")
    database.execute(
        "INSERT INTO devices (id, name, adapter, created_at) VALUES (1, 'A', 'fake', 0)"
    )
    return database


def test_constant_power_integrates_to_expected_energy(db):
    meter = EnergyMeter(db)
    # 100 W por 1 hora, uma leitura a cada 10 s.
    for i in range(361):
        meter.record(1, START + i * 10, 100.0)
    meter.flush()
    wh = db.scalar("SELECT SUM(wh) FROM energy_hour")
    assert wh == pytest.approx(100.0, rel=1e-6)


def test_gaps_are_not_extrapolated(db):
    meter = EnergyMeter(db, max_gap_sec=60)
    meter.record(1, START, 1000.0)
    meter.record(1, START + 3600, 1000.0)  # 1 h sem leituras
    meter.flush()
    # Só os 60 s máximos são contabilizados.
    assert db.scalar("SELECT SUM(wh) FROM energy_hour") == pytest.approx(1000 * 60 / 3600)


def test_offline_breaks_integration(db):
    meter = EnergyMeter(db)
    meter.record(1, START, 500.0)
    meter.record(1, START + 10, None)
    meter.record(1, START + 20, 500.0)
    meter.flush()
    assert db.scalar("SELECT SUM(wh) FROM energy_hour") == pytest.approx(0.0)


def test_report_buckets_by_local_hour_and_cost(db):
    meter = EnergyMeter(db)
    # 12:00-13:00 local (15:00 UTC) = 200 Wh
    db.execute("INSERT INTO energy_hour (device_id, ts, wh) VALUES (1, ?, 200)", (int(START),))
    report = energy_report(
        db, meter, range_key="today", tz="America/Sao_Paulo", now=START + 1800, tariff=1.0
    )
    assert report["total_kwh"] == pytest.approx(0.2)
    assert report["cost"] == pytest.approx(0.2)
    assert len(report["series"]) == 24
    noon = next(s for s in report["series"] if s["start"].startswith("2026-01-15T12:00"))
    assert noon["kwh"] == pytest.approx(0.2)


def test_report_includes_unflushed_current_minute(db):
    meter = EnergyMeter(db)
    meter.record(1, START, 3600.0)
    meter.record(1, START + 10, 3600.0)  # 10 Wh ainda em memória
    report = energy_report(
        db, meter, range_key="today", tz="America/Sao_Paulo", now=START + 10, tariff=1.0
    )
    assert report["total_kwh"] == pytest.approx(0.01)


def test_month_projection(db):
    meter = EnergyMeter(db)
    report = energy_report(
        db, meter, range_key="month", tz="America/Sao_Paulo", now=START, tariff=1.0
    )
    assert report["projected_cost"] == pytest.approx(0.0)
    assert len(report["series"]) == 31
