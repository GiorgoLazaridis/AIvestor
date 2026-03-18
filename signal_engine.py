"""
Multi-Timeframe Signal Engine mit Scoring-System.

Scoring (max 12 Punkte):
  4H-Trend-Alignment      = 3 Punkte  (stärkster Filter)
  1H-Struktur-Bestätigung = 2 Punkte
  15m EMA-Alignment       = 2 Punkte
  RSI-Momentum            = 2 Punkte
  MACD-Crossover          = 2 Punkte
  Volume-Bestätigung      = 1 Punkt
  ─────────────────────────────────
  MAX                     = 12 Punkte
  MIN zum Traden          = 7 Punkte
  High-Confidence         = 9+ Punkte
"""
import pandas as pd
from dataclasses import dataclass, field
from typing import Literal
import config


@dataclass
class Signal:
    action: Literal["BUY", "SELL", "NO TRADE"]
    symbol: str = ""
    score: int = 0
    confidence: str = ""       # "HIGH", "NORMAL", "NONE"
    entry: float = 0.0
    stop_loss: float = 0.0
    take_profit1: float = 0.0  # 2:1 → 50% schließen
    take_profit2: float = 0.0  # 4:1 → Rest schließen
    crv: float = 0.0
    atr: float = 0.0
    scored_signals: list = field(default_factory=list)
    reason: str = ""


def _score_4h_trend(df4h: pd.DataFrame) -> tuple[str | None, int, str]:
    """4H-Trend: stärkster Filter. Wert: 3 Punkte."""
    r = df4h.iloc[-1]
    bullish = r["ema_fast"] > r["ema_mid"] > r["ema_slow"] and r["close"] > r["ema_slow"]
    bearish = r["ema_fast"] < r["ema_mid"] < r["ema_slow"] and r["close"] < r["ema_slow"]

    # Mindestens letzte 3 Kerzen im Trend
    last3 = df4h.tail(3)
    trending_up   = all(last3["close"].diff().dropna() > 0)
    trending_down = all(last3["close"].diff().dropna() < 0)

    if bullish and trending_up:
        return "BUY", 3, "4H-Trend bullish + 3 steigende Kerzen"
    if bearish and trending_down:
        return "SELL", 3, "4H-Trend bearish + 3 fallende Kerzen"
    if bullish:
        return "BUY", 2, "4H-EMA bullish ausgerichtet"
    if bearish:
        return "SELL", 2, "4H-EMA bearish ausgerichtet"
    return None, 0, "4H: kein klarer Trend"


def _score_1h_structure(df1h: pd.DataFrame) -> tuple[str | None, int, str]:
    """1H-Struktur: Bestätigung. Wert: 2 Punkte."""
    r = df1h.iloc[-1]
    bullish = r["ema_fast"] > r["ema_mid"] and r["close"] > r["ema_mid"]
    bearish = r["ema_fast"] < r["ema_mid"] and r["close"] < r["ema_mid"]
    rsi_ok_bull = 40 < r["rsi"] < 70
    rsi_ok_bear = 30 < r["rsi"] < 60

    if bullish and rsi_ok_bull:
        return "BUY", 2, f"1H-Struktur bullish, RSI={r['rsi']:.1f}"
    if bearish and rsi_ok_bear:
        return "SELL", 2, f"1H-Struktur bearish, RSI={r['rsi']:.1f}"
    return None, 0, "1H: keine klare Struktur"


def _score_15m_ema(df15: pd.DataFrame) -> tuple[str | None, int, str]:
    """15m EMA-Alignment. Wert: 2 Punkte."""
    r = df15.iloc[-1]
    bullish = r["ema_fast"] > r["ema_mid"] > r["ema_slow"]
    bearish = r["ema_fast"] < r["ema_mid"] < r["ema_slow"]
    if bullish:
        return "BUY", 2, f"15m EMA bullish (9>{config.EMA_MID}>{config.EMA_SLOW})"
    if bearish:
        return "SELL", 2, f"15m EMA bearish (9<{config.EMA_MID}<{config.EMA_SLOW})"
    return None, 0, "15m EMA: kein Alignment"


def _score_rsi(df15: pd.DataFrame) -> tuple[str | None, int, str]:
    """RSI-Momentum. Wert: 1–2 Punkte."""
    r = df15.iloc[-1]
    rsi = r["rsi"]
    prev_rsi = df15.iloc[-2]["rsi"]

    if config.RSI_OVERSOLD < rsi < 55 and rsi > prev_rsi:
        return "BUY", 2, f"RSI={rsi:.1f} steigend aus überverkauft"
    if rsi < 45 and rsi > prev_rsi:
        return "BUY", 1, f"RSI={rsi:.1f} leicht steigend"
    if config.RSI_OVERBOUGHT > rsi > 45 and rsi < prev_rsi:
        return "SELL", 2, f"RSI={rsi:.1f} fallend aus überkauft"
    if rsi > 55 and rsi < prev_rsi:
        return "SELL", 1, f"RSI={rsi:.1f} leicht fallend"
    return None, 0, f"RSI={rsi:.1f} neutral"


def _score_macd(df15: pd.DataFrame) -> tuple[str | None, int, str]:
    """MACD-Crossover. Wert: 1–2 Punkte."""
    r    = df15.iloc[-1]
    prev = df15.iloc[-2]

    bullish_cross = prev["macd"] <= prev["macd_signal"] and r["macd"] > r["macd_signal"]
    bearish_cross = prev["macd"] >= prev["macd_signal"] and r["macd"] < r["macd_signal"]

    if bullish_cross:
        return "BUY", 2, f"MACD bullish Crossover (Hist={r['macd_hist']:.2f})"
    if bearish_cross:
        return "SELL", 2, f"MACD bearish Crossover (Hist={r['macd_hist']:.2f})"
    if r["macd"] > r["macd_signal"] and r["macd_hist"] > 0:
        return "BUY", 1, f"MACD über Signal, Hist={r['macd_hist']:.2f}"
    if r["macd"] < r["macd_signal"] and r["macd_hist"] < 0:
        return "SELL", 1, f"MACD unter Signal, Hist={r['macd_hist']:.2f}"
    return None, 0, "MACD: kein Signal"


def _score_volume(df15: pd.DataFrame) -> tuple[str | None, int, str]:
    """Volume-Bestätigung. Wert: 1 Punkt."""
    r = df15.iloc[-1]
    ratio = r["volume_ratio"]
    if ratio >= 1.5:
        return "CONFIRM", 1, f"Volume {ratio:.2f}x über Durchschnitt"
    return None, 0, f"Volume {ratio:.2f}x (zu gering)"


def generate_signal(symbol: str, dfs: dict) -> Signal:
    """
    Hauptlogik: Alle Timeframes auswerten, Score berechnen, Trade entscheiden.
    dfs = {"4h": df, "1h": df, "15m": df}
    """
    df4h = dfs["4h"]
    df1h = dfs["1h"]
    df15 = dfs["15m"]

    row15 = df15.iloc[-1]
    price = row15["close"]
    atr   = row15["atr"]

    checks = [
        _score_4h_trend(df4h),
        _score_1h_structure(df1h),
        _score_15m_ema(df15),
        _score_rsi(df15),
        _score_macd(df15),
        _score_volume(df15),
    ]

    buy_score  = 0
    sell_score = 0
    scored     = []

    for direction, pts, desc in checks:
        if direction == "BUY":
            buy_score += pts
            scored.append(f"+{pts} BUY  | {desc}")
        elif direction == "SELL":
            sell_score += pts
            scored.append(f"+{pts} SELL | {desc}")
        elif direction == "CONFIRM":
            buy_score  += pts
            sell_score += pts
            scored.append(f"+{pts} VOL  | {desc}")
        else:
            scored.append(f" 0    | {desc}")

    # Richtung bestimmen (Spot-only: SELL-Signale werden als NO TRADE behandelt)
    if buy_score >= config.MIN_SCORE and buy_score > sell_score:
        action = "BUY"
        score  = buy_score
    elif sell_score >= config.MIN_SCORE and sell_score > buy_score:
        return Signal(
            action="NO TRADE", symbol=symbol, score=sell_score,
            scored_signals=scored,
            reason=f"SELL-Signal (Score {sell_score}/12) — Spot-only, kein Short möglich"
        )
    else:
        dominant = max(buy_score, sell_score)
        return Signal(
            action="NO TRADE", symbol=symbol, score=dominant,
            scored_signals=scored,
            reason=f"Score {dominant}/12 — Minimum {config.MIN_SCORE} nicht erreicht"
        )

    # ── Adaptive SL/TP basierend auf Volatilitäts-Regime ────
    sl_mult = config.SL_ATR_MULTIPLIER
    if config.ADAPTIVE_SLTP and len(df15) >= config.VOL_LOOKBACK:
        recent_atr = df15["atr"].tail(config.VOL_LOOKBACK)
        atr_mean = recent_atr.mean()
        atr_std = recent_atr.std()
        if atr_std > 0 and atr_mean > 0:
            # Volatility z-score: >1 = sehr volatil, <-1 = sehr ruhig
            vol_z = (atr - atr_mean) / atr_std
            # Im ruhigen Markt engeren SL, im volatilen weiteren
            sl_mult = config.SL_ATR_MULTIPLIER + vol_z * 0.3
            sl_mult = max(config.SL_ATR_MIN, min(sl_mult, config.SL_ATR_MAX))

    # SL/TP berechnen
    sl  = price - atr * sl_mult
    tp1 = price + atr * sl_mult * config.TP1_RR
    tp2 = price + atr * sl_mult * config.TP2_RR

    sl_dist = abs(price - sl)
    tp1_dist = abs(tp1 - price)
    crv = tp1_dist / sl_dist if sl_dist > 0 else 0

    # Fee-Aware CRV: Fees von der Gewinnseite abziehen
    fee_cost_pct = config.TRADING_FEE_PCT * 2  # 1x Entry + 1x Exit = Round-Trip
    fee_usdt = price * (fee_cost_pct / 100)
    net_tp1_dist = tp1_dist - fee_usdt
    net_crv = net_tp1_dist / sl_dist if sl_dist > 0 else 0

    if net_crv < config.MIN_NET_CRV:
        return Signal(
            action="NO TRADE", symbol=symbol, score=score,
            entry=price, stop_loss=round(sl, 2),
            scored_signals=scored,
            reason=f"Netto-CRV {net_crv:.2f} unter Minimum {config.MIN_NET_CRV} (Fees: {fee_cost_pct:.2f}%)"
        )

    confidence = "HIGH" if score >= config.HIGH_CONF_SCORE else "NORMAL"

    return Signal(
        action=action,
        symbol=symbol,
        score=score,
        confidence=confidence,
        entry=round(price, 2),
        stop_loss=round(sl, 2),
        take_profit1=round(tp1, 2),
        take_profit2=round(tp2, 2),
        crv=round(crv, 2),
        atr=round(atr, 2),
        scored_signals=scored,
        reason=f"Score {score}/12 ({confidence}) | CRV {crv:.1f}:1 (netto {net_crv:.1f}:1) | ATR={atr:.2f} | SL×{sl_mult:.1f}"
    )
