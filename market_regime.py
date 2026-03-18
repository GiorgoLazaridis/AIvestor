"""
Markt-Regime Erkennung — Profi-Ansatz.

Logik:
  BTC ist der Marktführer. Wenn BTC in einem klaren Abwärtstrend ist,
  verlieren 80% aller Altcoins ebenfalls. In diesem Regime nur Shorts
  oder gar nicht handeln.

Regime:
  BULL   → Klarer Aufwärtstrend, Longs bevorzugen
  BEAR   → Klarer Abwärtstrend, keine Longs
  NEUTRAL→ Seitwärts, sehr selektiv handeln
"""
import pandas as pd
from dataclasses import dataclass
from data_fetcher import fetch_klines
from indicators import calculate_all


@dataclass
class MarketRegime:
    regime: str          # "BULL", "BEAR", "NEUTRAL"
    btc_trend: str       # "UP", "DOWN", "SIDEWAYS"
    btc_price: float
    btc_above_ema50: bool
    btc_rsi: float
    allow_longs: bool
    allow_shorts: bool
    detail: str


def detect() -> MarketRegime:
    """
    Analysiert BTC auf dem 4H-Chart als Marktbarometer.
    Entscheidung basiert auf:
      1. EMA-Ausrichtung (9 > 21 > 50 = bullish)
      2. Preis über/unter EMA 50
      3. RSI-Niveau
      4. Letzte 5 Kerzen: Trend-Richtung
    """
    df = fetch_klines("BTCUSDT", "4h", limit=100)
    df = calculate_all(df)
    r  = df.iloc[-1]

    price       = r["close"]
    above_ema50 = price > r["ema_slow"]
    rsi         = r["rsi"]

    # EMA-Ausrichtung
    ema_bull = r["ema_fast"] > r["ema_mid"] > r["ema_slow"]
    ema_bear = r["ema_fast"] < r["ema_mid"] < r["ema_slow"]

    # Momentum: letzte 5 Kerzen
    last5 = df.tail(5)["close"]
    momentum = (last5.iloc[-1] - last5.iloc[0]) / last5.iloc[0] * 100

    # Entscheidung
    if ema_bull and above_ema50 and rsi > 45:
        regime      = "BULL"
        btc_trend   = "UP"
        allow_longs = True
        allow_shorts= False
        detail = f"BTC bullish | EMA aufsteigend | RSI={rsi:.1f} | Mom={momentum:+.2f}%"

    elif ema_bear and not above_ema50 and rsi < 55:
        regime      = "BEAR"
        btc_trend   = "DOWN"
        allow_longs = False
        allow_shorts= True
        detail = f"BTC bearish | EMA absteigend | RSI={rsi:.1f} | Mom={momentum:+.2f}%"

    else:
        regime      = "NEUTRAL"
        btc_trend   = "SIDEWAYS"
        # Neutral: nur bei sehr starken Signalen handeln
        allow_longs = rsi < 50 and above_ema50
        allow_shorts= rsi > 50 and not above_ema50
        detail = f"BTC seitwärts | RSI={rsi:.1f} | Mom={momentum:+.2f}% | Selektiv"

    return MarketRegime(
        regime=regime,
        btc_trend=btc_trend,
        btc_price=round(price, 2),
        btc_above_ema50=above_ema50,
        btc_rsi=round(rsi, 1),
        allow_longs=allow_longs,
        allow_shorts=allow_shorts,
        detail=detail
    )
