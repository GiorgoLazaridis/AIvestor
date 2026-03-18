"""Tests for risk_manager — drawdown limits, Kelly sizing, circuit breaker."""
import os
import pytest
import risk_manager as rm
import config


@pytest.fixture(autouse=True)
def clean_state(tmp_path, monkeypatch):
    test_file = str(tmp_path / "risk_state.json")
    monkeypatch.setattr(rm, "RISK_STATE_FILE", test_file)
    yield


class TestDrawdownLimits:
    def test_can_trade_when_no_drawdown(self):
        state = rm.RiskState(daily_pnl_usdt=0, starting_balance=1000)
        allowed, reason = rm.can_trade(state, 1000)
        assert allowed is True

    def test_blocked_after_daily_drawdown(self, monkeypatch):
        monkeypatch.setattr(config, "MAX_DAILY_DRAWDOWN_PCT", 3.0)
        state = rm.RiskState(daily_pnl_usdt=-35, starting_balance=1000)
        allowed, reason = rm.can_trade(state, 965)
        assert allowed is False
        assert "Daily Drawdown" in reason

    def test_allowed_if_under_limit(self, monkeypatch):
        monkeypatch.setattr(config, "MAX_DAILY_DRAWDOWN_PCT", 3.0)
        state = rm.RiskState(daily_pnl_usdt=-20, starting_balance=1000)
        allowed, _ = rm.can_trade(state, 980)
        assert allowed is True


class TestRecordTrade:
    def test_record_updates_pnl(self):
        state = rm.RiskState()
        state = rm.record_trade(state, "BTCUSDT", 50.0, 1000.0)
        assert state.daily_pnl_usdt == 50.0
        assert state.weekly_pnl_usdt == 50.0
        assert len(state.trade_history) == 1
        assert state.trade_history[0]["win"] is True

    def test_record_losing_trade(self):
        state = rm.RiskState()
        state = rm.record_trade(state, "ETHUSDT", -20.0, 500.0)
        assert state.daily_pnl_usdt == -20.0
        assert state.trade_history[0]["win"] is False

    def test_history_capped_at_200(self):
        state = rm.RiskState()
        for i in range(250):
            state = rm.record_trade(state, "BTCUSDT", 1.0, 100.0)
        assert len(state.trade_history) == 200


class TestKellySizing:
    def test_fallback_when_few_trades(self, monkeypatch):
        monkeypatch.setattr(config, "USE_KELLY_SIZING", True)
        monkeypatch.setattr(config, "KELLY_MIN_TRADES", 20)
        state = rm.RiskState()
        for i in range(5):
            state = rm.record_trade(state, "BTC", 10.0, 100.0)
        pct = rm.calc_kelly_risk_pct(state)
        assert pct == config.KELLY_FALLBACK_PCT

    def test_kelly_with_good_stats(self, monkeypatch):
        monkeypatch.setattr(config, "USE_KELLY_SIZING", True)
        monkeypatch.setattr(config, "KELLY_MIN_TRADES", 5)
        monkeypatch.setattr(config, "KELLY_FRACTION", 0.25)
        state = rm.RiskState()
        # 60% win rate, avg win 3%, avg loss 1.5% → good Kelly
        for i in range(6):
            state = rm.record_trade(state, "BTC", 30.0, 1000.0)
        for i in range(4):
            state = rm.record_trade(state, "BTC", -15.0, 1000.0)

        pct = rm.calc_kelly_risk_pct(state)
        assert pct > 0
        assert pct <= config.ACCOUNT_RISK_HIGH

    def test_kelly_disabled_returns_base(self, monkeypatch):
        monkeypatch.setattr(config, "USE_KELLY_SIZING", False)
        state = rm.RiskState()
        pct = rm.calc_kelly_risk_pct(state)
        assert pct == config.ACCOUNT_RISK_BASE


class TestTradeStats:
    def test_empty_stats(self):
        state = rm.RiskState()
        stats = rm.get_trade_stats(state)
        assert stats["trades"] == 0
        assert stats["win_rate"] == 0

    def test_stats_calculation(self):
        state = rm.RiskState()
        state = rm.record_trade(state, "BTC", 100.0, 1000.0)
        state = rm.record_trade(state, "ETH", -30.0, 500.0)
        stats = rm.get_trade_stats(state)
        assert stats["trades"] == 2
        assert stats["win_rate"] == 50.0
        assert stats["profit_factor"] > 1.0
