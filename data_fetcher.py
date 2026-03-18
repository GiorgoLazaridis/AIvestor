import requests
import pandas as pd
from concurrent.futures import ThreadPoolExecutor
import config

BINANCE_BASE = "https://testnet.binance.vision" if config.TESTNET else "https://api.binance.com"


def fetch_klines(symbol: str, interval: str, limit: int = config.CANDLES_LIMIT) -> pd.DataFrame:
    url = f"{BINANCE_BASE}/api/v3/klines"
    r = requests.get(url, params={"symbol": symbol, "interval": interval, "limit": limit}, timeout=10)
    r.raise_for_status()
    df = pd.DataFrame(r.json(), columns=[
        "open_time","open","high","low","close","volume",
        "close_time","quote_vol","trades","taker_base","taker_quote","ignore"
    ])
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
    for c in ["open","high","low","close","volume"]:
        df[c] = df[c].astype(float)
    return df[["open_time","open","high","low","close","volume"]].set_index("open_time")


def fetch_current_price(symbol: str) -> float:
    r = requests.get(f"{BINANCE_BASE}/api/v3/ticker/price", params={"symbol": symbol}, timeout=10)
    r.raise_for_status()
    return float(r.json()["price"])


def fetch_all_timeframes(symbol: str) -> dict:
    """Holt 4H, 1H und 15m parallel für ein Symbol."""
    timeframes = [
        ("4h",  config.TF_TREND),
        ("1h",  config.TF_STRUCT),
        ("15m", config.TF_ENTRY),
    ]
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {tf: pool.submit(fetch_klines, symbol, interval) for tf, interval in timeframes}
        return {tf: fut.result() for tf, fut in futures.items()}
