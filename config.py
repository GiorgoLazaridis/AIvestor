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
MIN_SCORE         = 7   # von max. 12
HIGH_CONF_SCORE   = 9   # "starkes" Signal → größere Position

# ── Risiko-Management ────────────────────────────────────────
ACCOUNT_RISK_BASE    = float(os.getenv("ACCOUNT_RISK_PERCENT", 1.0))  # % bei normalem Signal
ACCOUNT_RISK_HIGH    = 1.5   # % bei high-confidence Signal
MAX_TRADE_USDT       = float(os.getenv("MAX_TRADE_USDT", 100.0))
MAX_OPEN_POSITIONS   = 3     # Max 3 gleichzeitig, aber nie 2 aus gleicher Gruppe
MAX_PER_GROUP        = 1     # Korrelations-Schutz: max 1 Trade pro Gruppe
SL_ATR_MULTIPLIER    = 1.5
TRAIL_ATR_MULTIPLIER = 1.0   # Trailing Stop: 1x ATR hinter Preis
TP1_RR               = 2.0   # Erste TP bei 2:1 → 50% schließen
TP2_RR               = 4.0   # Zweite TP bei 4:1 → Rest schließen
MIN_CRV              = 2.0

# ── Loop ─────────────────────────────────────────────────────
LOOP_INTERVAL_SECONDS = 60
