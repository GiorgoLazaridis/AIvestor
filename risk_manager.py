"""
Fortgeschrittenes Risiko-Management:
- Drawdown-Circuit-Breaker (Tages-/Wochen-Limit)
- Kelly-Criterion Positionsgröße
- Trade-Statistiken für adaptive Sizing
"""
import json
import os
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, asdict, field

import config


RISK_STATE_FILE = "risk_state.json"


@dataclass
class TradeResult:
    symbol: str
    pnl_pct: float       # P&L in % des Entry-Werts
    pnl_usdt: float
    closed_at: str
    win: bool


@dataclass
class RiskState:
    daily_pnl_usdt: float = 0.0
    weekly_pnl_usdt: float = 0.0
    daily_reset_date: str = ""
    weekly_reset_date: str = ""
    paused_until: str = ""          # ISO datetime — Trading pausiert bis
    pause_reason: str = ""
    trade_history: list = field(default_factory=list)   # Liste von TradeResult-Dicts
    starting_balance: float = 0.0   # Balance am Tagesanfang


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _week_start() -> str:
    now = datetime.now(timezone.utc)
    monday = now - timedelta(days=now.weekday())
    return monday.strftime("%Y-%m-%d")


def load_state() -> RiskState:
    if not os.path.exists(RISK_STATE_FILE):
        return RiskState()
    try:
        with open(RISK_STATE_FILE, "r") as f:
            data = json.load(f)
            # Trade history bleibt als list[dict]
            return RiskState(**data)
    except Exception:
        return RiskState()


def save_state(state: RiskState) -> None:
    with open(RISK_STATE_FILE, "w") as f:
        json.dump(asdict(state), f, indent=2)


def check_and_reset(state: RiskState, current_balance: float) -> RiskState:
    """Tages-/Wochen-Reset wenn nötig."""
    today = _today()
    week = _week_start()

    if state.daily_reset_date != today:
        state.daily_pnl_usdt = 0.0
        state.daily_reset_date = today
        state.starting_balance = current_balance

    if state.weekly_reset_date != week:
        state.weekly_pnl_usdt = 0.0
        state.weekly_reset_date = week

    # Pause abgelaufen?
    if state.paused_until:
        try:
            pause_end = datetime.fromisoformat(state.paused_until)
            if datetime.now(timezone.utc) >= pause_end:
                state.paused_until = ""
                state.pause_reason = ""
        except ValueError:
            state.paused_until = ""

    save_state(state)
    return state


def can_trade(state: RiskState, current_balance: float) -> tuple[bool, str]:
    """
    Prüft ob Trading erlaubt ist.
    Returns: (erlaubt, grund)
    """
    # Pause aktiv?
    if state.paused_until:
        return False, f"PAUSED: {state.pause_reason} (bis {state.paused_until})"

    # Tages-Drawdown
    ref_balance = state.starting_balance if state.starting_balance > 0 else current_balance
    if ref_balance > 0:
        daily_dd_pct = abs(state.daily_pnl_usdt) / ref_balance * 100
        if state.daily_pnl_usdt < 0 and daily_dd_pct >= config.MAX_DAILY_DRAWDOWN_PCT:
            # Pause bis morgen 00:00 UTC
            tomorrow = datetime.now(timezone.utc).replace(
                hour=0, minute=0, second=0, microsecond=0
            ) + timedelta(days=1)
            state.paused_until = tomorrow.isoformat()
            state.pause_reason = f"Daily Drawdown {daily_dd_pct:.1f}% >= {config.MAX_DAILY_DRAWDOWN_PCT}%"
            save_state(state)
            return False, state.pause_reason

        # Wochen-Drawdown
        weekly_dd_pct = abs(state.weekly_pnl_usdt) / ref_balance * 100
        if state.weekly_pnl_usdt < 0 and weekly_dd_pct >= config.MAX_WEEKLY_DRAWDOWN_PCT:
            # Pause bis nächsten Montag
            now = datetime.now(timezone.utc)
            days_until_monday = (7 - now.weekday()) % 7 or 7
            next_monday = (now + timedelta(days=days_until_monday)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            state.paused_until = next_monday.isoformat()
            state.pause_reason = f"Weekly Drawdown {weekly_dd_pct:.1f}% >= {config.MAX_WEEKLY_DRAWDOWN_PCT}%"
            save_state(state)
            return False, state.pause_reason

    return True, ""


def record_trade(state: RiskState, symbol: str, pnl_usdt: float, entry_value: float) -> RiskState:
    """Registriert einen abgeschlossenen Trade."""
    pnl_pct = (pnl_usdt / entry_value * 100) if entry_value > 0 else 0

    result = TradeResult(
        symbol=symbol,
        pnl_pct=pnl_pct,
        pnl_usdt=pnl_usdt,
        closed_at=datetime.now(timezone.utc).isoformat(),
        win=pnl_usdt > 0,
    )

    state.daily_pnl_usdt += pnl_usdt
    state.weekly_pnl_usdt += pnl_usdt
    state.trade_history.append(asdict(result))

    # History auf max. 200 Trades begrenzen
    if len(state.trade_history) > 200:
        state.trade_history = state.trade_history[-200:]

    save_state(state)
    return state


def calc_kelly_risk_pct(state: RiskState) -> float:
    """
    Kelly-Criterion Positionsgröße.
    f* = W - (1-W)/R
    W = Win-Rate, R = Avg-Win / Avg-Loss
    Returns: Optimaler Risk% (bereits mit KELLY_FRACTION skaliert)
    """
    if not config.USE_KELLY_SIZING:
        return config.ACCOUNT_RISK_BASE

    history = state.trade_history
    if len(history) < config.KELLY_MIN_TRADES:
        return config.KELLY_FALLBACK_PCT

    wins = [t for t in history if t["win"]]
    losses = [t for t in history if not t["win"]]

    if not losses or not wins:
        return config.KELLY_FALLBACK_PCT

    win_rate = len(wins) / len(history)
    avg_win = sum(abs(t["pnl_pct"]) for t in wins) / len(wins)
    avg_loss = sum(abs(t["pnl_pct"]) for t in losses) / len(losses)

    if avg_loss == 0:
        return config.KELLY_FALLBACK_PCT

    payoff_ratio = avg_win / avg_loss
    kelly = win_rate - (1 - win_rate) / payoff_ratio

    # Kelly kann negativ sein → nicht traden
    if kelly <= 0:
        return 0.0

    # Fractional Kelly mit Clamp
    risk_pct = kelly * 100 * config.KELLY_FRACTION
    risk_pct = max(0.5, min(risk_pct, config.ACCOUNT_RISK_HIGH))

    return round(risk_pct, 2)


def get_trade_stats(state: RiskState) -> dict:
    """Gibt aktuelle Trade-Statistiken zurück."""
    history = state.trade_history
    if not history:
        return {"trades": 0, "win_rate": 0, "avg_win": 0, "avg_loss": 0,
                "profit_factor": 0, "kelly_risk_pct": config.KELLY_FALLBACK_PCT}

    wins = [t for t in history if t["win"]]
    losses = [t for t in history if not t["win"]]

    total_wins = sum(t["pnl_usdt"] for t in wins) if wins else 0
    total_losses = abs(sum(t["pnl_usdt"] for t in losses)) if losses else 0
    profit_factor = total_wins / total_losses if total_losses > 0 else float("inf")

    return {
        "trades": len(history),
        "win_rate": round(len(wins) / len(history) * 100, 1) if history else 0,
        "avg_win": round(sum(t["pnl_pct"] for t in wins) / len(wins), 2) if wins else 0,
        "avg_loss": round(sum(t["pnl_pct"] for t in losses) / len(losses), 2) if losses else 0,
        "profit_factor": round(profit_factor, 2),
        "kelly_risk_pct": calc_kelly_risk_pct(state),
    }
