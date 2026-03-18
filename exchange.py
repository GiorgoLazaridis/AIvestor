"""
Binance-Client Wrapper.
Wechselt automatisch zwischen Testnet und Live basierend auf config.TESTNET.
"""
from binance.client import Client
import config

_client = None


def get_client() -> Client:
    global _client
    if _client is None:
        _client = Client(
            api_key=config.BINANCE_API_KEY,
            api_secret=config.BINANCE_API_SECRET,
            testnet=config.TESTNET
        )
    return _client


def get_balance_usdt() -> float:
    """Gibt den freien USDT-Bestand zurück."""
    client = get_client()
    balance = client.get_asset_balance(asset="USDT")
    return float(balance["free"])


def get_balance_btc() -> float:
    """Gibt den freien BTC-Bestand zurück."""
    client = get_client()
    balance = client.get_asset_balance(asset="BTC")
    return float(balance["free"])


def get_symbol_info(symbol: str = "BTCUSDT") -> dict:
    """Gibt Handelsbeschränkungen für das Symbol zurück (min qty, step size etc.)."""
    client = get_client()
    info = client.get_symbol_info(symbol)
    filters = {f["filterType"]: f for f in info["filters"]}
    return {
        "min_qty": float(filters["LOT_SIZE"]["minQty"]),
        "step_size": float(filters["LOT_SIZE"]["stepSize"]),
        "min_notional": float(filters.get("NOTIONAL", {}).get("minNotional", 10.0)),
        "tick_size": float(filters["PRICE_FILTER"]["tickSize"]),
    }
