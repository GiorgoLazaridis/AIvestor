"""Tests for position_manager — CRUD operations and data integrity."""
import json
import os
import pytest
import position_manager as pm


@pytest.fixture(autouse=True)
def clean_positions(tmp_path, monkeypatch):
    """Use a temp file for each test to avoid side effects."""
    test_file = str(tmp_path / "positions.json")
    monkeypatch.setattr(pm, "POSITIONS_FILE", test_file)
    yield
    if os.path.exists(test_file):
        os.remove(test_file)


def _make_pos(symbol="BTCUSDT", active=True, **kwargs) -> pm.Position:
    defaults = dict(
        active=active, symbol=symbol, side="BUY",
        entry_price=50000.0, quantity=0.01, quantity_remaining=0.01,
        stop_loss=49000.0, trailing_sl=49000.0,
        take_profit1=52000.0, take_profit2=54000.0,
        atr=500.0, score=8, confidence="NORMAL",
    )
    defaults.update(kwargs)
    return pm.Position(**defaults)


class TestSaveLoad:
    def test_save_and_load_single(self):
        pos = _make_pos()
        pm.save("BTCUSDT", pos)
        loaded = pm.load("BTCUSDT")
        assert loaded.active is True
        assert loaded.entry_price == 50000.0
        assert loaded.symbol == "BTCUSDT"

    def test_load_nonexistent_returns_default(self):
        pos = pm.load("XYZUSDT")
        assert pos.active is False
        assert pos.symbol == ""

    def test_load_all_empty(self):
        assert pm.load_all() == {}

    def test_save_multiple(self):
        pm.save("BTCUSDT", _make_pos("BTCUSDT"))
        pm.save("ETHUSDT", _make_pos("ETHUSDT"))
        all_pos = pm.load_all()
        assert len(all_pos) == 2
        assert "BTCUSDT" in all_pos
        assert "ETHUSDT" in all_pos


class TestRemove:
    def test_remove_existing(self):
        pm.save("BTCUSDT", _make_pos())
        pm.remove("BTCUSDT")
        assert pm.load("BTCUSDT").active is False

    def test_remove_nonexistent_no_error(self):
        pm.remove("DOESNTEXIST")


class TestCountActive:
    def test_count_zero(self):
        assert pm.count_active() == 0

    def test_count_active_only(self):
        pm.save("BTCUSDT", _make_pos(active=True))
        pm.save("ETHUSDT", _make_pos("ETHUSDT", active=False))
        assert pm.count_active() == 1


class TestDataIntegrity:
    def test_trailing_order_id_persists(self):
        pos = _make_pos(trailing_order_id="12345")
        pm.save("BTCUSDT", pos)
        loaded = pm.load("BTCUSDT")
        assert loaded.trailing_order_id == "12345"

    def test_tp1_hit_flag_persists(self):
        pos = _make_pos(tp1_hit=True, pnl_realized=150.0)
        pm.save("BTCUSDT", pos)
        loaded = pm.load("BTCUSDT")
        assert loaded.tp1_hit is True
        assert loaded.pnl_realized == 150.0

    def test_corrupt_json_returns_empty(self, tmp_path, monkeypatch):
        test_file = str(tmp_path / "corrupt.json")
        monkeypatch.setattr(pm, "POSITIONS_FILE", test_file)
        with open(test_file, "w") as f:
            f.write("{broken json!!")
        assert pm.load_all() == {}
