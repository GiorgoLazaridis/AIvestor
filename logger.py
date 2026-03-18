import json
import os
from datetime import datetime, timezone


LOG_FILE = "trades_log.json"


def _load() -> list:
    if not os.path.exists(LOG_FILE):
        return []
    with open(LOG_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except Exception:
            return []


def _save(logs: list) -> None:
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(logs, f, indent=2, ensure_ascii=False)


def log_signal(signal) -> None:
    logs = _load()
    logs.append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": "SIGNAL",
        "symbol": signal.symbol,
        "action": signal.action,
        "score": signal.score,
        "confidence": signal.confidence,
        "entry": signal.entry,
        "stop_loss": signal.stop_loss,
        "take_profit1": signal.take_profit1,
        "take_profit2": signal.take_profit2,
        "crv": signal.crv,
        "reason": signal.reason,
    })
    _save(logs)


def log_event(symbol: str, event: str, detail: str = "") -> None:
    logs = _load()
    logs.append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": event,
        "symbol": symbol,
        "detail": detail,
    })
    _save(logs)
