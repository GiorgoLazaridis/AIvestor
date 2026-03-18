"""
Performance-Tracking und Reporting.
Erfasst tägliche P&L, berechnet Metriken, erstellt Reports.
"""
import json
import os
from datetime import datetime, timezone
from dataclasses import dataclass, asdict

import config


PERFORMANCE_FILE = "performance.json"


@dataclass
class DailyRecord:
    date: str
    starting_balance: float
    ending_balance: float
    pnl_usdt: float
    pnl_pct: float
    trades_opened: int
    trades_closed: int
    wins: int
    losses: int


def _load() -> list[dict]:
    if not os.path.exists(PERFORMANCE_FILE):
        return []
    try:
        with open(PERFORMANCE_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return []


def _save(records: list[dict]) -> None:
    # Max 365 Tage behalten
    if len(records) > 365:
        records = records[-365:]
    with open(PERFORMANCE_FILE, "w") as f:
        json.dump(records, f, indent=2)


def record_day(starting_balance: float, ending_balance: float,
               trades_opened: int, trades_closed: int, wins: int, losses: int) -> None:
    """Speichert den Tagesabschluss."""
    records = _load()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    pnl = ending_balance - starting_balance
    pnl_pct = (pnl / starting_balance * 100) if starting_balance > 0 else 0

    day = DailyRecord(
        date=today,
        starting_balance=round(starting_balance, 2),
        ending_balance=round(ending_balance, 2),
        pnl_usdt=round(pnl, 2),
        pnl_pct=round(pnl_pct, 2),
        trades_opened=trades_opened,
        trades_closed=trades_closed,
        wins=wins,
        losses=losses,
    )

    # Heutigen Eintrag updaten oder neuen hinzufügen
    if records and records[-1].get("date") == today:
        records[-1] = asdict(day)
    else:
        records.append(asdict(day))

    _save(records)


def calc_metrics(records: list[dict] | None = None) -> dict:
    """Berechnet Performance-Metriken über alle Tageseinträge."""
    if records is None:
        records = _load()
    if not records:
        return {}

    total_pnl = sum(r["pnl_usdt"] for r in records)
    start_bal = records[0]["starting_balance"]
    end_bal = records[-1]["ending_balance"]
    total_return_pct = ((end_bal - start_bal) / start_bal * 100) if start_bal > 0 else 0

    # Max Drawdown
    peak = 0
    max_dd = 0
    running = start_bal
    for r in records:
        running += r["pnl_usdt"]
        peak = max(peak, running)
        dd = (peak - running) / peak * 100 if peak > 0 else 0
        max_dd = max(max_dd, dd)

    # Win-Rate
    total_wins = sum(r["wins"] for r in records)
    total_losses = sum(r["losses"] for r in records)
    total_trades = total_wins + total_losses
    win_rate = (total_wins / total_trades * 100) if total_trades > 0 else 0

    # Profitable Tage
    profitable_days = sum(1 for r in records if r["pnl_usdt"] > 0)
    total_days = len(records)

    # Monthly average (annualisiert)
    if total_days >= 7:
        daily_avg = total_pnl / total_days
        monthly_avg = daily_avg * 30
        monthly_pct = (monthly_avg / start_bal * 100) if start_bal > 0 else 0
    else:
        monthly_avg = 0
        monthly_pct = 0

    # Sharpe-ähnliche Ratio (daily returns)
    if total_days >= 7:
        daily_returns = [r["pnl_pct"] for r in records]
        mean_ret = sum(daily_returns) / len(daily_returns)
        variance = sum((r - mean_ret) ** 2 for r in daily_returns) / len(daily_returns)
        std_ret = variance ** 0.5
        # Annualisiert (365 Tage Krypto)
        sharpe = (mean_ret / std_ret * (365 ** 0.5)) if std_ret > 0 else 0
    else:
        sharpe = 0

    return {
        "days": total_days,
        "total_pnl_usdt": round(total_pnl, 2),
        "total_return_pct": round(total_return_pct, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "win_rate": round(win_rate, 1),
        "total_trades": total_trades,
        "profitable_days": profitable_days,
        "profitable_days_pct": round(profitable_days / total_days * 100, 1) if total_days > 0 else 0,
        "monthly_avg_pct": round(monthly_pct, 2),
        "sharpe_ratio": round(sharpe, 2),
    }


def print_report() -> None:
    """Gibt einen Performance-Report auf der Konsole aus."""
    m = calc_metrics()
    if not m:
        print("  Noch keine Performance-Daten.")
        return

    print(f"\n  {'─'*50}")
    print(f"  PERFORMANCE REPORT ({m['days']} Tage)")
    print(f"  {'─'*50}")
    print(f"  Gesamt P&L:       {m['total_pnl_usdt']:+.2f} USDT ({m['total_return_pct']:+.1f}%)")
    print(f"  Max Drawdown:     {m['max_drawdown_pct']:.1f}%")
    print(f"  Win-Rate:         {m['win_rate']:.1f}% ({m['total_trades']} Trades)")
    print(f"  Profitable Tage:  {m['profitable_days']}/{m['days']} ({m['profitable_days_pct']:.0f}%)")
    print(f"  Monatl. Schnitt:  {m['monthly_avg_pct']:+.2f}%")
    print(f"  Sharpe Ratio:     {m['sharpe_ratio']:.2f}")
    print(f"  {'─'*50}")
