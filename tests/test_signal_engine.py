"""Tests for signal_engine — score calculation and signal generation."""
import numpy as np
import pandas as pd
import pytest
import config
from signal_engine import (
    generate_signal, _score_4h_trend, _score_1h_structure,
    _score_15m_ema, _score_rsi, _score_macd, _score_volume,
)


def _make_df(rows=5, **overrides):
    """Create a minimal DataFrame with indicator columns."""
    defaults = dict(
        close=50000.0, open=49900.0, high=50100.0, low=49800.0, volume=100.0,
        ema_fast=50050.0, ema_mid=49900.0, ema_slow=49700.0,
        rsi=50.0, macd=0.5, macd_signal=0.3, macd_hist=0.2,
        volume_avg=80.0, volume_ratio=1.25, atr=500.0,
    )
    defaults.update(overrides)
    data = {k: [v] * rows for k, v in defaults.items()}
    return pd.DataFrame(data)


class TestScore4hTrend:
    def test_bullish_with_rising_candles(self):
        df = _make_df(5, ema_fast=50050, ema_mid=49900, ema_slow=49700)
        # Make last 3 candles rising
        df["close"] = [49800, 49900, 50000, 50100, 50200]
        direction, pts, _ = _score_4h_trend(df)
        assert direction == "BUY"
        assert pts == 3

    def test_bearish_with_falling_candles(self):
        df = _make_df(5, ema_fast=49700, ema_mid=49900, ema_slow=50050)
        df["close"] = [50200, 50100, 50000, 49900, 49600]
        direction, pts, _ = _score_4h_trend(df)
        assert direction == "SELL"
        assert pts == 3

    def test_no_trend_returns_zero(self):
        df = _make_df(5, ema_fast=50000, ema_mid=50000, ema_slow=50000)
        direction, pts, _ = _score_4h_trend(df)
        assert direction is None
        assert pts == 0


class TestScore1hStructure:
    def test_bullish_structure(self):
        df = _make_df(1, ema_fast=50050, ema_mid=49900, close=50000, rsi=55)
        direction, pts, _ = _score_1h_structure(df)
        assert direction == "BUY"
        assert pts == 2

    def test_bearish_structure(self):
        df = _make_df(1, ema_fast=49800, ema_mid=50000, close=49900, rsi=45)
        direction, pts, _ = _score_1h_structure(df)
        assert direction == "SELL"
        assert pts == 2


class TestScore15mEma:
    def test_bullish_alignment(self):
        df = _make_df(1, ema_fast=50100, ema_mid=50000, ema_slow=49900)
        direction, pts, _ = _score_15m_ema(df)
        assert direction == "BUY"
        assert pts == 2

    def test_bearish_alignment(self):
        df = _make_df(1, ema_fast=49800, ema_mid=49900, ema_slow=50000)
        direction, pts, _ = _score_15m_ema(df)
        assert direction == "SELL"
        assert pts == 2


class TestScoreRsi:
    def test_rising_from_oversold(self):
        df = _make_df(2, rsi=42)
        df.loc[0, "rsi"] = 38
        df.loc[1, "rsi"] = 42
        direction, pts, _ = _score_rsi(df)
        assert direction == "BUY"
        assert pts == 2

    def test_neutral_rsi(self):
        df = _make_df(2, rsi=50)
        direction, pts, _ = _score_rsi(df)
        assert direction is None
        assert pts == 0


class TestScoreMacd:
    def test_bullish_crossover(self):
        df = _make_df(2)
        df.loc[0, "macd"] = -0.1
        df.loc[0, "macd_signal"] = 0.0
        df.loc[1, "macd"] = 0.2
        df.loc[1, "macd_signal"] = 0.1
        df.loc[1, "macd_hist"] = 0.1
        direction, pts, _ = _score_macd(df)
        assert direction == "BUY"
        assert pts == 2


class TestScoreVolume:
    def test_high_volume_confirms(self):
        df = _make_df(1, volume_ratio=2.0)
        direction, pts, _ = _score_volume(df)
        assert direction == "CONFIRM"
        assert pts == 1

    def test_low_volume_no_confirm(self):
        df = _make_df(1, volume_ratio=0.8)
        direction, pts, _ = _score_volume(df)
        assert direction is None
        assert pts == 0


class TestGenerateSignal:
    def _bullish_dfs(self):
        """Create DataFrames that produce a strong BUY signal."""
        df4h = _make_df(5, ema_fast=50100, ema_mid=50000, ema_slow=49800)
        df4h["close"] = [49900, 50000, 50100, 50200, 50300]

        df1h = _make_df(2, ema_fast=50100, ema_mid=50000, close=50200, rsi=55)

        df15 = _make_df(2,
            ema_fast=50100, ema_mid=50000, ema_slow=49900,
            rsi=42, macd=0.2, macd_signal=0.1, macd_hist=0.1,
            volume_ratio=2.0, atr=500.0, close=50200,
        )
        df15.loc[0, "rsi"] = 38
        df15.loc[0, "macd"] = -0.1
        df15.loc[0, "macd_signal"] = 0.0
        return {"4h": df4h, "1h": df1h, "15m": df15}

    def test_strong_buy_signal(self):
        dfs = self._bullish_dfs()
        signal = generate_signal("BTCUSDT", dfs)
        assert signal.action == "BUY"
        assert signal.score >= config.MIN_SCORE
        assert signal.confidence in ("HIGH", "NORMAL")
        assert signal.stop_loss < signal.entry
        assert signal.take_profit1 > signal.entry
        assert signal.take_profit2 > signal.take_profit1

    def test_no_trade_when_score_low(self):
        # Neutral DataFrames — no alignment
        df = _make_df(5, ema_fast=50000, ema_mid=50000, ema_slow=50000, rsi=50,
                       macd=0, macd_signal=0, macd_hist=0, volume_ratio=0.5, atr=500)
        dfs = {"4h": df.copy(), "1h": df.copy(), "15m": df.copy()}
        signal = generate_signal("BTCUSDT", dfs)
        assert signal.action == "NO TRADE"

    def test_signal_has_correct_symbol(self):
        dfs = self._bullish_dfs()
        signal = generate_signal("ETHUSDT", dfs)
        assert signal.symbol == "ETHUSDT"
