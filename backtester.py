"""
Backtesting-Engine für AIvestor.

Simuliert die exakte Strategie auf historischen Daten:
- Klines-Download von Binance (mit lokalem Cache)
- Walk-Forward-Simulation auf 15m-Kerzen
- Realistische Fees und Slippage
- Performance-Report mit Sharpe, Drawdown, Win-Rate

Verwendung:
    python backtester.py                    # Standard-Backtest
    python backtester.py --start 2024-01-01 # Ab bestimmtem Datum
    python backtester.py --symbol BTCUSDT   # Einzelnes Symbol
"""
import os
import sys
import argparse
import json
import math
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field

import requests
import pandas as pd

# Projekt-Imports (ohne Binance-Client!)
import config
from indicators import calculate_all
from signal_engine import generate_signal


# ── Daten-Download ──────────────────────────────────────────

def _download_klines(symbol: str, interval: str, start_ms: int, end_ms: int) -> list:
    """Holt Klines direkt von Binance Public API (kein API Key nötig)."""
    url = "https://api.binance.com/api/v3/klines"
    all_data = []
    current = start_ms

    while current < end_ms:
        params = {
            "symbol": symbol, "interval": interval,
            "startTime": current, "endTime": end_ms, "limit": 1000,
        }
        r = requests.get(url, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        if not data:
            break
        all_data.extend(data)
        current = data[-1][6] + 1  # close_time + 1ms

    return all_data


def _klines_to_df(data: list) -> pd.DataFrame:
    df = pd.DataFrame(data, columns=[
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "quote_vol", "trades", "taker_base", "taker_quote", "ignore"
    ])
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = df[c].astype(float)
    return df[["open_time", "open", "high", "low", "close", "volume"]].set_index("open_time")


def load_data(symbol: str, interval: str, start_date: str, end_date: str) -> pd.DataFrame:
    """Lädt Klines mit Cache."""
    os.makedirs(config.BACKTEST_DATA_DIR, exist_ok=True)
    cache_file = os.path.join(
        config.BACKTEST_DATA_DIR,
        f"{symbol}_{interval}_{start_date}_{end_date}.parquet"
    )

    if os.path.exists(cache_file):
        return pd.read_parquet(cache_file)

    print(f"  Downloading {symbol} {interval} ({start_date} → {end_date})...")
    start_ms = int(datetime.strptime(start_date, "%Y-%m-%d").replace(
        tzinfo=timezone.utc).timestamp() * 1000)
    end_ms = int(datetime.strptime(end_date, "%Y-%m-%d").replace(
        tzinfo=timezone.utc).timestamp() * 1000)

    raw = _download_klines(symbol, interval, start_ms, end_ms)
    df = _klines_to_df(raw)
    df.to_parquet(cache_file)
    return df


# ── Simulations-Engine ──────────────────────────────────────

@dataclass
class SimPosition:
    symbol: str
    entry_price: float
    quantity: float
    quantity_remaining: float
    stop_loss: float
    trailing_sl: float
    take_profit1: float
    take_profit2: float
    atr: float
    tp1_hit: bool = False
    pnl_realized: float = 0.0
    entry_time: str = ""
    score: int = 0


@dataclass
class BacktestResult:
    initial_balance: float
    final_balance: float
    total_return_pct: float
    monthly_avg_pct: float
    max_drawdown_pct: float
    total_trades: int
    wins: int
    losses: int
    win_rate: float
    avg_win_pct: float
    avg_loss_pct: float
    profit_factor: float
    sharpe_ratio: float
    best_trade_pct: float
    worst_trade_pct: float
    avg_trade_duration_h: float
    equity_curve: list = field(default_factory=list)
    trades_log: list = field(default_factory=list)


def _apply_slippage(price: float, direction: str) -> float:
    """Simulierter Slippage: gegen uns."""
    slip = config.BACKTEST_SLIPPAGE_PCT / 100
    if direction == "BUY":
        return price * (1 + slip)
    return price * (1 - slip)


def _apply_fee(notional: float) -> float:
    return notional * config.TRADING_FEE_PCT / 100


def run_backtest(
    symbols: list[str] | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    initial_balance: float | None = None,
) -> BacktestResult:
    """
    Führt einen Walk-Forward-Backtest durch.
    Iteriert über 15m-Kerzen und simuliert die exakte Bot-Logik.
    """
    symbols = symbols or config.SYMBOLS
    start = start_date or config.BACKTEST_START
    end = end_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    balance = initial_balance or config.BACKTEST_INITIAL_USDT

    print(f"\n{'='*60}")
    print(f"  BACKTEST: {start} → {end}")
    print(f"  Symbole: {', '.join(symbols)}")
    print(f"  Startkapital: ${balance:,.2f}")
    print(f"  Fees: {config.TRADING_FEE_PCT}% | Slippage: {config.BACKTEST_SLIPPAGE_PCT}%")
    print(f"{'='*60}\n")

    # Daten laden (braucht etwas für den ersten Download)
    print("  Lade historische Daten...")
    # Startdatum 60 Tage zurück für Indikator-Warmup
    warmup_start = (datetime.strptime(start, "%Y-%m-%d") - timedelta(days=60)).strftime("%Y-%m-%d")

    all_data = {}
    for symbol in symbols:
        all_data[symbol] = {}
        for interval in [config.TF_ENTRY, config.TF_STRUCT, config.TF_TREND]:
            df = load_data(symbol, interval, warmup_start, end)
            df = calculate_all(df)
            all_data[symbol][interval] = df

    # BTC-Regime-Daten
    if "BTCUSDT" not in all_data:
        btc_4h = load_data("BTCUSDT", "4h", warmup_start, end)
        btc_4h = calculate_all(btc_4h)
    else:
        btc_4h = all_data["BTCUSDT"]["4h"]

    # ── Walk-Forward Simulation ─────────────────────────────
    # Iteriere über 15m-Kerzen ab Startdatum
    entry_df = all_data[symbols[0]][config.TF_ENTRY]
    start_ts = pd.Timestamp(start, tz="UTC")
    sim_times = entry_df.loc[entry_df.index >= start_ts].index

    positions: dict[str, SimPosition] = {}
    equity = balance
    peak_equity = balance
    max_dd = 0

    equity_curve = []
    trades_log = []
    all_pnl_pcts = []

    check_interval = 4  # Alle 4 Kerzen (=1h) neue Signale suchen
    candle_count = 0

    print(f"  Simuliere {len(sim_times)} Zeitschritte...")

    for ts in sim_times:
        candle_count += 1

        # ── Offene Positionen managen (jede Kerze) ─────────
        for sym in list(positions.keys()):
            pos = positions[sym]
            sym_data = all_data.get(sym, {}).get(config.TF_ENTRY)
            if sym_data is None or ts not in sym_data.index:
                continue

            candle = sym_data.loc[ts]
            high = candle["high"]
            low = candle["low"]
            close = candle["close"]

            # Stop-Loss getriggert?
            if low <= pos.trailing_sl:
                fill_price = _apply_slippage(pos.trailing_sl, "SELL")
                pnl = (fill_price - pos.entry_price) * pos.quantity_remaining
                pnl -= _apply_fee(fill_price * pos.quantity_remaining)
                pos.pnl_realized += pnl
                equity += pos.pnl_realized
                entry_val = pos.entry_price * pos.quantity
                pnl_pct = pos.pnl_realized / entry_val * 100 if entry_val > 0 else 0
                all_pnl_pcts.append(pnl_pct)
                trades_log.append({
                    "symbol": sym, "entry": pos.entry_price,
                    "exit": fill_price, "pnl_pct": round(pnl_pct, 2),
                    "pnl_usdt": round(pos.pnl_realized, 2),
                    "reason": "TRAILING_SL" if pos.tp1_hit else "SL",
                    "entry_time": pos.entry_time, "exit_time": str(ts),
                })
                del positions[sym]
                continue

            # TP1 Check
            if not pos.tp1_hit and high >= pos.take_profit1:
                fill_price = _apply_slippage(pos.take_profit1, "SELL")
                qty_close = pos.quantity * 0.5
                pnl = (fill_price - pos.entry_price) * qty_close
                pnl -= _apply_fee(fill_price * qty_close)
                pos.pnl_realized += pnl
                pos.quantity_remaining -= qty_close
                pos.tp1_hit = True
                pos.trailing_sl = pos.entry_price  # Breakeven
                pos.stop_loss = pos.entry_price

            # TP2 Check
            if pos.tp1_hit and high >= pos.take_profit2:
                fill_price = _apply_slippage(pos.take_profit2, "SELL")
                pnl = (fill_price - pos.entry_price) * pos.quantity_remaining
                pnl -= _apply_fee(fill_price * pos.quantity_remaining)
                pos.pnl_realized += pnl
                equity += pos.pnl_realized
                entry_val = pos.entry_price * pos.quantity
                pnl_pct = pos.pnl_realized / entry_val * 100 if entry_val > 0 else 0
                all_pnl_pcts.append(pnl_pct)
                trades_log.append({
                    "symbol": sym, "entry": pos.entry_price,
                    "exit": fill_price, "pnl_pct": round(pnl_pct, 2),
                    "pnl_usdt": round(pos.pnl_realized, 2),
                    "reason": "TP2",
                    "entry_time": pos.entry_time, "exit_time": str(ts),
                })
                del positions[sym]
                continue

            # Trailing Stop nachziehen
            if pos.tp1_hit or (pos.entry_price > 0 and
                    (close - pos.entry_price) / (pos.entry_price - pos.stop_loss) >= config.TRAIL_ACTIVATION_RR
                    if pos.entry_price != pos.stop_loss else False):
                new_trail = close - (pos.atr * config.TRAIL_ATR_MULTIPLIER)
                step_threshold = pos.trailing_sl * (1 + config.TRAIL_STEP_PCT / 100)
                if new_trail > pos.trailing_sl and new_trail >= step_threshold:
                    pos.trailing_sl = new_trail

            # Time-based Exit
            try:
                opened = pd.Timestamp(pos.entry_time)
                hours = (ts - opened).total_seconds() / 3600
                if not pos.tp1_hit and hours >= config.MAX_TRADE_HOURS and close >= pos.entry_price:
                    fill_price = _apply_slippage(close, "SELL")
                    pnl = (fill_price - pos.entry_price) * pos.quantity_remaining
                    pnl -= _apply_fee(fill_price * pos.quantity_remaining)
                    pos.pnl_realized += pnl
                    equity += pos.pnl_realized
                    entry_val = pos.entry_price * pos.quantity
                    pnl_pct = pos.pnl_realized / entry_val * 100 if entry_val > 0 else 0
                    all_pnl_pcts.append(pnl_pct)
                    trades_log.append({
                        "symbol": sym, "entry": pos.entry_price,
                        "exit": fill_price, "pnl_pct": round(pnl_pct, 2),
                        "pnl_usdt": round(pos.pnl_realized, 2),
                        "reason": f"TIME_EXIT_{hours:.0f}h",
                        "entry_time": pos.entry_time, "exit_time": str(ts),
                    })
                    del positions[sym]
                    continue

                if hours >= config.STALE_TRADE_HOURS:
                    fill_price = _apply_slippage(close, "SELL")
                    pnl = (fill_price - pos.entry_price) * pos.quantity_remaining
                    pnl -= _apply_fee(fill_price * pos.quantity_remaining)
                    pos.pnl_realized += pnl
                    equity += pos.pnl_realized
                    entry_val = pos.entry_price * pos.quantity
                    pnl_pct = pos.pnl_realized / entry_val * 100 if entry_val > 0 else 0
                    all_pnl_pcts.append(pnl_pct)
                    trades_log.append({
                        "symbol": sym, "entry": pos.entry_price,
                        "exit": fill_price, "pnl_pct": round(pnl_pct, 2),
                        "pnl_usdt": round(pos.pnl_realized, 2),
                        "reason": f"STALE_{hours:.0f}h",
                        "entry_time": pos.entry_time, "exit_time": str(ts),
                    })
                    del positions[sym]
                    continue
            except (ValueError, TypeError):
                pass

        # ── Neue Signale (alle check_interval Kerzen) ──────
        if candle_count % check_interval != 0:
            # Equity-Curve trotzdem tracken
            open_pnl = sum(
                (all_data[s][config.TF_ENTRY].loc[ts]["close"] - p.entry_price) * p.quantity_remaining
                for s, p in positions.items()
                if ts in all_data.get(s, {}).get(config.TF_ENTRY, pd.DataFrame()).index
            )
            equity_curve.append({"time": str(ts), "equity": round(equity + open_pnl, 2)})
            peak_equity = max(peak_equity, equity + open_pnl)
            dd = (peak_equity - (equity + open_pnl)) / peak_equity * 100 if peak_equity > 0 else 0
            max_dd = max(max_dd, dd)
            continue

        # BTC-Regime
        btc_rows = btc_4h.loc[btc_4h.index <= ts]
        if len(btc_rows) < 5:
            continue
        btc_r = btc_rows.iloc[-1]
        ema_bull = btc_r["ema_fast"] > btc_r["ema_mid"] > btc_r["ema_slow"]
        btc_above_ema50 = btc_r["close"] > btc_r["ema_slow"]
        allow_longs = ema_bull and btc_above_ema50 and btc_r["rsi"] > 45

        if not allow_longs:
            continue

        if len(positions) >= config.MAX_OPEN_POSITIONS:
            continue

        # Signale für alle Symbole prüfen
        for symbol in symbols:
            if symbol in positions:
                continue
            if len(positions) >= config.MAX_OPEN_POSITIONS:
                break

            # Korrelations-Check
            grp = None
            for g, syms in config.SYMBOL_GROUPS.items():
                if symbol in syms:
                    grp = g
                    break
            if grp:
                grp_open = any(
                    s in positions for s in config.SYMBOL_GROUPS.get(grp, []) if s != symbol
                )
                if grp_open:
                    continue

            # Daten bis zum aktuellen Zeitpunkt schneiden
            dfs = {}
            valid = True
            for tf_key, tf_val in [("4h", config.TF_TREND), ("1h", config.TF_STRUCT), ("15m", config.TF_ENTRY)]:
                sym_df = all_data.get(symbol, {}).get(tf_val)
                if sym_df is None:
                    valid = False
                    break
                subset = sym_df.loc[sym_df.index <= ts]
                if len(subset) < 60:
                    valid = False
                    break
                dfs[tf_key] = subset

            if not valid:
                continue

            try:
                signal = generate_signal(symbol, dfs)
            except Exception:
                continue

            if signal.action != "BUY":
                continue

            # Position eröffnen
            entry_price = _apply_slippage(signal.entry, "BUY")
            sl_dist = abs(entry_price - signal.stop_loss)
            if sl_dist == 0:
                continue

            risk_usdt = equity * (config.ACCOUNT_RISK_BASE / 100)
            risk_usdt = min(risk_usdt, config.MAX_TRADE_USDT * (config.ACCOUNT_RISK_BASE / 100))
            qty = risk_usdt / sl_dist
            notional = qty * entry_price

            # Fee abziehen
            equity -= _apply_fee(notional)

            positions[symbol] = SimPosition(
                symbol=symbol,
                entry_price=entry_price,
                quantity=qty,
                quantity_remaining=qty,
                stop_loss=signal.stop_loss,
                trailing_sl=signal.stop_loss,
                take_profit1=signal.take_profit1,
                take_profit2=signal.take_profit2,
                atr=signal.atr,
                entry_time=str(ts),
                score=signal.score,
            )

        # Equity Curve
        open_pnl = sum(
            (all_data[s][config.TF_ENTRY].loc[ts]["close"] - p.entry_price) * p.quantity_remaining
            for s, p in positions.items()
            if ts in all_data.get(s, {}).get(config.TF_ENTRY, pd.DataFrame()).index
        )
        equity_curve.append({"time": str(ts), "equity": round(equity + open_pnl, 2)})
        peak_equity = max(peak_equity, equity + open_pnl)
        dd = (peak_equity - (equity + open_pnl)) / peak_equity * 100 if peak_equity > 0 else 0
        max_dd = max(max_dd, dd)

    # ── Offene Positionen am Ende schließen ─────────────────
    for sym, pos in list(positions.items()):
        sym_data = all_data.get(sym, {}).get(config.TF_ENTRY)
        if sym_data is not None and len(sym_data) > 0:
            last_price = sym_data.iloc[-1]["close"]
            pnl = (last_price - pos.entry_price) * pos.quantity_remaining
            pnl -= _apply_fee(last_price * pos.quantity_remaining)
            pos.pnl_realized += pnl
            equity += pos.pnl_realized
            entry_val = pos.entry_price * pos.quantity
            pnl_pct = pos.pnl_realized / entry_val * 100 if entry_val > 0 else 0
            all_pnl_pcts.append(pnl_pct)
            trades_log.append({
                "symbol": sym, "entry": pos.entry_price,
                "exit": last_price, "pnl_pct": round(pnl_pct, 2),
                "pnl_usdt": round(pos.pnl_realized, 2),
                "reason": "END_OF_BACKTEST",
                "entry_time": pos.entry_time, "exit_time": str(sim_times[-1]),
            })

    # ── Metriken berechnen ──────────────────────────────────
    total_trades = len(trades_log)
    wins = [t for t in trades_log if t["pnl_usdt"] > 0]
    losses = [t for t in trades_log if t["pnl_usdt"] <= 0]

    win_rate = len(wins) / total_trades * 100 if total_trades > 0 else 0
    avg_win = sum(t["pnl_pct"] for t in wins) / len(wins) if wins else 0
    avg_loss = sum(t["pnl_pct"] for t in losses) / len(losses) if losses else 0

    total_win_usdt = sum(t["pnl_usdt"] for t in wins)
    total_loss_usdt = abs(sum(t["pnl_usdt"] for t in losses))
    profit_factor = total_win_usdt / total_loss_usdt if total_loss_usdt > 0 else float("inf")

    initial = initial_balance or config.BACKTEST_INITIAL_USDT
    total_return = (equity - initial) / initial * 100

    # Dauer berechnen
    days = (sim_times[-1] - sim_times[0]).days if len(sim_times) > 1 else 1
    months = max(days / 30, 1)
    monthly_avg = total_return / months

    # Sharpe
    if all_pnl_pcts and len(all_pnl_pcts) > 1:
        mean_pnl = sum(all_pnl_pcts) / len(all_pnl_pcts)
        var = sum((p - mean_pnl) ** 2 for p in all_pnl_pcts) / len(all_pnl_pcts)
        std_pnl = var ** 0.5
        trades_per_year = len(all_pnl_pcts) / (days / 365) if days > 0 else 0
        sharpe = (mean_pnl / std_pnl * (trades_per_year ** 0.5)) if std_pnl > 0 else 0
    else:
        sharpe = 0

    # Trade-Dauer
    durations = []
    for t in trades_log:
        try:
            entry_t = pd.Timestamp(t["entry_time"])
            exit_t = pd.Timestamp(t["exit_time"])
            durations.append((exit_t - entry_t).total_seconds() / 3600)
        except Exception:
            pass
    avg_duration = sum(durations) / len(durations) if durations else 0

    best = max(all_pnl_pcts) if all_pnl_pcts else 0
    worst = min(all_pnl_pcts) if all_pnl_pcts else 0

    return BacktestResult(
        initial_balance=initial,
        final_balance=round(equity, 2),
        total_return_pct=round(total_return, 2),
        monthly_avg_pct=round(monthly_avg, 2),
        max_drawdown_pct=round(max_dd, 2),
        total_trades=total_trades,
        wins=len(wins),
        losses=len(losses),
        win_rate=round(win_rate, 1),
        avg_win_pct=round(avg_win, 2),
        avg_loss_pct=round(avg_loss, 2),
        profit_factor=round(profit_factor, 2),
        sharpe_ratio=round(sharpe, 2),
        best_trade_pct=round(best, 2),
        worst_trade_pct=round(worst, 2),
        avg_trade_duration_h=round(avg_duration, 1),
        equity_curve=equity_curve,
        trades_log=trades_log,
    )


def print_result(result: BacktestResult) -> None:
    """Gibt den Backtest-Report aus."""
    r = result
    print(f"\n{'='*60}")
    print(f"  BACKTEST ERGEBNIS")
    print(f"{'='*60}")
    print(f"  Startkapital:     ${r.initial_balance:,.2f}")
    print(f"  Endkapital:       ${r.final_balance:,.2f}")
    print(f"  Gesamt-Return:    {r.total_return_pct:+.2f}%")
    print(f"  Monatl. Schnitt:  {r.monthly_avg_pct:+.2f}%")
    print(f"  Max Drawdown:     {r.max_drawdown_pct:.2f}%")
    print(f"{'─'*60}")
    print(f"  Trades:           {r.total_trades}")
    print(f"  Gewinner:         {r.wins} ({r.win_rate}%)")
    print(f"  Verlierer:        {r.losses}")
    print(f"  Avg Win:          {r.avg_win_pct:+.2f}%")
    print(f"  Avg Loss:         {r.avg_loss_pct:+.2f}%")
    print(f"  Bester Trade:     {r.best_trade_pct:+.2f}%")
    print(f"  Schlechtester:    {r.worst_trade_pct:+.2f}%")
    print(f"  Profit Factor:    {r.profit_factor:.2f}")
    print(f"  Sharpe Ratio:     {r.sharpe_ratio:.2f}")
    print(f"  Avg Dauer:        {r.avg_trade_duration_h:.1f}h")
    print(f"{'='*60}")

    # Bewertung
    if r.profit_factor >= 2.0 and r.win_rate >= 50:
        print(f"\n  BEWERTUNG: Starke Strategie")
    elif r.profit_factor >= 1.5 and r.win_rate >= 45:
        print(f"\n  BEWERTUNG: Solide Strategie")
    elif r.profit_factor >= 1.0:
        print(f"\n  BEWERTUNG: Grenzwertig — Optimierung empfohlen")
    else:
        print(f"\n  BEWERTUNG: Unprofitabel — Strategie überarbeiten!")

    # Top-Trades
    if r.trades_log:
        print(f"\n  Top 5 Trades:")
        sorted_trades = sorted(r.trades_log, key=lambda t: t["pnl_usdt"], reverse=True)
        for t in sorted_trades[:5]:
            print(f"    {t['symbol']:10s} {t['pnl_usdt']:+8.2f} USDT ({t['pnl_pct']:+.1f}%) | {t['reason']}")

        print(f"\n  Worst 5 Trades:")
        for t in sorted_trades[-5:]:
            print(f"    {t['symbol']:10s} {t['pnl_usdt']:+8.2f} USDT ({t['pnl_pct']:+.1f}%) | {t['reason']}")


def save_result(result: BacktestResult, filename: str = "backtest_result.json") -> None:
    """Speichert das Ergebnis als JSON."""
    with open(filename, "w") as f:
        json.dump({
            "summary": {
                "initial_balance": result.initial_balance,
                "final_balance": result.final_balance,
                "total_return_pct": result.total_return_pct,
                "monthly_avg_pct": result.monthly_avg_pct,
                "max_drawdown_pct": result.max_drawdown_pct,
                "total_trades": result.total_trades,
                "win_rate": result.win_rate,
                "profit_factor": result.profit_factor,
                "sharpe_ratio": result.sharpe_ratio,
            },
            "trades": result.trades_log,
            "equity_curve": result.equity_curve[-500:],  # Letzte 500 Punkte
        }, f, indent=2)
    print(f"\n  Ergebnis gespeichert: {filename}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AIvestor Backtester")
    parser.add_argument("--start", default=config.BACKTEST_START, help="Startdatum (YYYY-MM-DD)")
    parser.add_argument("--end", default=datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    parser.add_argument("--symbol", help="Einzelnes Symbol testen")
    parser.add_argument("--balance", type=float, default=config.BACKTEST_INITIAL_USDT)
    args = parser.parse_args()

    symbols = [args.symbol] if args.symbol else config.SYMBOLS

    result = run_backtest(
        symbols=symbols,
        start_date=args.start,
        end_date=args.end,
        initial_balance=args.balance,
    )
    print_result(result)
    save_result(result)
