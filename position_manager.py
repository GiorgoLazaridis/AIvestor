"""
Verwaltet alle offenen Positionen in positions.json.
Unterstützt jetzt Multi-Symbol und Partial-TP.
"""
import json
import os
from dataclasses import dataclass, asdict, field
from typing import Optional

POSITIONS_FILE = "positions.json"


@dataclass
class Position:
    active: bool          = False
    symbol: str           = ""
    side: str             = ""
    entry_price: float    = 0.0
    quantity: float       = 0.0
    quantity_remaining: float = 0.0   # nach Partial-TP
    stop_loss: float      = 0.0
    trailing_sl: float    = 0.0       # aktueller Trailing-Stop
    take_profit1: float   = 0.0
    take_profit2: float   = 0.0
    tp1_hit: bool         = False     # wurde TP1 bereits ausgeführt?
    atr: float            = 0.0
    oco_order_id: str     = ""
    entry_order_id: str   = ""
    score: int            = 0
    confidence: str       = ""
    opened_at: str        = ""
    pnl_realized: float   = 0.0       # Bereits realisierter P&L (nach TP1)


def load_all() -> dict[str, Position]:
    """Gibt alle Positionen als {symbol: Position} zurück."""
    if not os.path.exists(POSITIONS_FILE):
        return {}
    with open(POSITIONS_FILE, "r") as f:
        try:
            data = json.load(f)
            return {k: Position(**v) for k, v in data.items()}
        except Exception:
            return {}


def save_all(positions: dict[str, Position]) -> None:
    with open(POSITIONS_FILE, "w") as f:
        json.dump({k: asdict(v) for k, v in positions.items()}, f, indent=2)


def load(symbol: str) -> Position:
    return load_all().get(symbol, Position())


def save(symbol: str, pos: Position) -> None:
    all_pos = load_all()
    all_pos[symbol] = pos
    save_all(all_pos)


def remove(symbol: str) -> None:
    all_pos = load_all()
    all_pos.pop(symbol, None)
    save_all(all_pos)


def count_active() -> int:
    return sum(1 for p in load_all().values() if p.active)
