import os
from dotenv import load_dotenv

load_dotenv()

# API
BINANCE_API_KEY    = os.getenv("BINANCE_API_KEY", "")
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET", "")

# Modus: "testnet" oder "live"
TRADING_MODE = os.getenv("TRADING_MODE", "testnet")
TESTNET      = TRADING_MODE != "live"

# ── Multi-Symbol ─────────────────────────────────────────────
# Gruppiert nach Korrelation — max. 1 Trade pro Gruppe gleichzeitig
# Gruppe A: BTC-Korreliert (bewegen sich fast identisch)
# Gruppe B: Altcoins Mid-Cap (etwas unabhängiger)
# Gruppe C: High-Volatility (eigene Dynamik, höheres Potenzial)
SYMBOL_GROUPS = {
    "A": ["BTCUSDT", "ETHUSDT", "BNBUSDT"],      # Stark korreliert
    "B": ["SOLUSDT", "AVAXUSDT", "LINKUSDT"],     # Mittel korreliert
    "C": ["XRPUSDT", "DOTUSDT"],                  # Eigene Dynamik
}
SYMBOLS = [s for group in SYMBOL_GROUPS.values() for s in group]

# ── Multi-Timeframe ──────────────────────────────────────────
TF_TREND  = "4h"   # Übergeordneter Trend
TF_STRUCT = "1h"   # Struktur / Bestätigung
TF_ENTRY  = "15m"  # Präziser Entry
CANDLES_LIMIT = 120

# ── Indikatoren ──────────────────────────────────────────────
EMA_FAST         = 9
EMA_MID          = 21
EMA_SLOW         = 50
RSI_PERIOD       = 14
RSI_OVERSOLD     = 35
RSI_OVERBOUGHT   = 65
MACD_FAST        = 12
MACD_SLOW        = 26
MACD_SIGNAL      = 9
VOLUME_AVG_PERIOD = 20

# ── Signal-Scoring ───────────────────────────────────────────
# Jedes Signal hat Gewichtung 1–3. Mindest-Score zum Traden:
MIN_SCORE         = 8   # von max. 14 (optimiert via Backtest)
HIGH_CONF_SCORE   = 11  # "starkes" Signal → größere Position

# ── Risiko-Management ────────────────────────────────────────
ACCOUNT_RISK_BASE    = float(os.getenv("ACCOUNT_RISK_PERCENT", 1.0))  # % bei normalem Signal
ACCOUNT_RISK_HIGH    = 1.5   # % bei high-confidence Signal
MAX_TRADE_USDT       = float(os.getenv("MAX_TRADE_USDT", 100.0))
MAX_OPEN_POSITIONS   = 3     # Max 3 gleichzeitig, aber nie 2 aus gleicher Gruppe
MAX_PER_GROUP        = 1     # Korrelations-Schutz: max 1 Trade pro Gruppe
SL_ATR_MULTIPLIER    = 1.0   # Engerer SL (optimiert via Backtest)
TRAIL_ATR_MULTIPLIER = 2.5   # Trailing Stop: 2.5x ATR hinter Preis (optimiert v2)
TP1_RR               = 2.0   # Erste TP bei 2:1 → 50% schließen
TP2_RR               = 4.0   # Zweite TP bei 4:1 → Rest schließen
MIN_CRV              = 2.0

# ── Drawdown-Limits (Circuit Breaker) ──────────────────────
MAX_DAILY_DRAWDOWN_PCT  = float(os.getenv("MAX_DAILY_DRAWDOWN", 3.0))
MAX_WEEKLY_DRAWDOWN_PCT = float(os.getenv("MAX_WEEKLY_DRAWDOWN", 6.0))

# ── Kelly-Positionsgröße ────────────────────────────────────
USE_KELLY_SIZING     = True        # Kelly statt fixem Risk%
KELLY_FRACTION       = 0.25        # 25% Kelly (konservativ)
KELLY_MIN_TRADES     = 20          # Mindest-Trades bevor Kelly aktiv wird
KELLY_FALLBACK_PCT   = 1.0         # Fallback-Risk% bis genug Daten

# ── Zeitbasierte Exits ──────────────────────────────────────
MAX_TRADE_HOURS      = 48          # TP1 nicht erreicht → Breakeven-Exit (optimiert)
STALE_TRADE_HOURS    = 72          # Force-Close nach 72h (optimiert)

# ── Adaptive SL/TP ──────────────────────────────────────────
ADAPTIVE_SLTP        = True        # SL/TP an Volatilität anpassen
SL_ATR_MIN           = 1.0         # Minimum SL in ATR (ruhiger Markt)
SL_ATR_MAX           = 2.5         # Maximum SL in ATR (volatiler Markt)
VOL_LOOKBACK         = 20          # Perioden für Volatilitäts-Berechnung

# ── Enhanced Trailing Stop ───────────────────────────────────
TRAIL_STEP_PCT       = 0.8         # SL in 0.8%-Stufen nachziehen (optimiert v2)
TRAIL_ACTIVATION_RR  = 1.5         # Trailing erst nach 1.5:1 R:R aktivieren (optimiert)

# ── Fees ─────────────────────────────────────────────────────
TRADING_FEE_PCT      = 0.10        # Binance Maker/Taker Fee in %
MIN_NET_CRV          = 1.8         # Mindest-CRV NACH Abzug der Fees

# ── Pyramiding (Gewinner aufstocken) ─────────────────────────
PYRAMIDING_ENABLED   = False       # Vorsichtig — erst nach Backtest aktivieren
PYRAMID_MAX_ADDS     = 1           # Max. 1x Nachkauf pro Position
PYRAMID_TRIGGER_RR   = 1.5         # Nachkauf bei 1.5:1 R:R im Plus

# ── Loop ─────────────────────────────────────────────────────
LOOP_INTERVAL_SECONDS = 60

# ── Backtest ─────────────────────────────────────────────────
BACKTEST_START        = "2024-01-01"   # Startdatum für Backtest (2+ Jahre)
BACKTEST_INITIAL_USDT = 1000.0         # Start-Kapital
BACKTEST_SLIPPAGE_PCT = 0.05           # Simulierter Slippage in %
BACKTEST_DATA_DIR     = "backtest_data" # Cache-Ordner für historische Daten
