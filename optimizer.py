"""
Parameter-Optimizer v2: Testet systematisch verschiedene Konfigurationen
und findet die profitabelste Kombination.

Strategie: Mehrstufige Suche mit Out-of-Sample-Validierung
1. Grob: SL, TP1, TP2, MIN_SCORE (auf Train-Daten)
2. Fein: Trailing, Timing (auf Train-Daten)
3. OOS-Validierung: Bester Parameter-Satz auf ungesehenen Daten
"""
import sys
import time
import itertools
from datetime import datetime, timezone, timedelta

import config
from backtester import run_backtest


def _test_params(params: dict, symbols: list, start: str, end: str, balance: float) -> dict:
    """Setzt Parameter, laeuft Backtest, gibt Metriken zurueck."""
    # Config temporaer ueberschreiben
    originals = {}
    for key, val in params.items():
        originals[key] = getattr(config, key)
        setattr(config, key, val)

    try:
        result = run_backtest(
            symbols=symbols, start_date=start,
            end_date=end, initial_balance=balance,
        )
        return {
            "params": params,
            "return_pct": result.total_return_pct,
            "monthly_pct": result.monthly_avg_pct,
            "max_dd": result.max_drawdown_pct,
            "trades": result.total_trades,
            "win_rate": result.win_rate,
            "profit_factor": result.profit_factor,
            "sharpe": result.sharpe_ratio,
            "avg_win": result.avg_win_pct,
            "avg_loss": result.avg_loss_pct,
        }
    except Exception as e:
        return {"params": params, "error": str(e)}
    finally:
        # Originals wiederherstellen
        for key, val in originals.items():
            setattr(config, key, val)


def _print_result(r: dict, rank: int = 0) -> None:
    if "error" in r:
        print(f"  ERROR: {r['error']}")
        return
    prefix = f"  #{rank}" if rank else "  "
    pf = r['profit_factor']
    print(f"{prefix} PF={pf:.2f} | Return={r['return_pct']:+.1f}% | "
          f"Monthly={r['monthly_pct']:+.2f}% | DD={r['max_dd']:.1f}% | "
          f"WR={r['win_rate']:.0f}% | Trades={r['trades']} | "
          f"Sharpe={r['sharpe']:.2f}")
    p = r['params']
    print(f"       SL={p.get('SL_ATR_MULTIPLIER','?')} | TP1={p.get('TP1_RR','?')} | "
          f"TP2={p.get('TP2_RR','?')} | Score={p.get('MIN_SCORE','?')} | "
          f"Trail={p.get('TRAIL_ATR_MULTIPLIER','?')}")


def optimize(symbols=None, start="2025-01-01", end=None, balance=1000.0, validate=True):
    symbols = symbols or config.SYMBOLS
    end = end or datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Out-of-Sample Split: 70% Train, 30% Test
    start_dt = datetime.strptime(start, "%Y-%m-%d")
    end_dt = datetime.strptime(end, "%Y-%m-%d")
    total_days = (end_dt - start_dt).days

    if validate and total_days > 60:
        train_days = int(total_days * 0.7)
        train_end = (start_dt + timedelta(days=train_days)).strftime("%Y-%m-%d")
        test_start = train_end
    else:
        train_end = end
        test_start = None
        validate = False

    print(f"\n{'='*65}")
    print(f"  OPTIMIZER v2: Parameter-Suche mit OOS-Validierung")
    print(f"  {start} -> {end} | {len(symbols)} Symbole | ${balance}")
    if validate:
        print(f"  Train: {start} -> {train_end} ({int(total_days * 0.7)} Tage)")
        print(f"  Test:  {test_start} -> {end} ({total_days - int(total_days * 0.7)} Tage)")
    print(f"{'='*65}")

    # ── Phase 1: SL + Score Grobraster ──────────────────────
    print(f"\n  Phase 1: SL-Multiplier + MIN_SCORE...")
    phase1_grid = {
        "SL_ATR_MULTIPLIER": [1.0, 1.5, 2.0, 2.5],
        "MIN_SCORE": [5, 6, 7, 8],
    }
    keys = list(phase1_grid.keys())
    combos = list(itertools.product(*[phase1_grid[k] for k in keys]))
    results = []

    for i, vals in enumerate(combos):
        params = dict(zip(keys, vals))
        sys.stdout.write(f"\r  [{i+1}/{len(combos)}] SL={vals[0]}, Score={vals[1]}...")
        sys.stdout.flush()
        r = _test_params(params, symbols, start, train_end, balance)
        if "error" not in r:
            results.append(r)

    # Filter: nur Ergebnisse mit mindestens 10 Trades (PF=inf bei 0 Trades ist kein Ergebnis)
    results = [r for r in results if r.get("trades", 0) >= 10]
    results.sort(key=lambda r: r["profit_factor"], reverse=True)
    print(f"\n\n  Phase 1 Top 5:")
    for i, r in enumerate(results[:5], 1):
        _print_result(r, i)

    if not results:
        print("  KEINE gueltige Kombination gefunden!")
        return {}
    best1 = results[0]["params"]

    # ── Phase 2: TP1 + TP2 ──────────────────────────────────
    print(f"\n  Phase 2: TP1/TP2 Ratio (SL={best1['SL_ATR_MULTIPLIER']}, Score={best1['MIN_SCORE']})...")
    phase2_grid = {
        "TP1_RR": [1.5, 2.0, 2.5, 3.0],
        "TP2_RR": [3.0, 4.0, 5.0, 6.0],
    }
    keys2 = list(phase2_grid.keys())
    combos2 = list(itertools.product(*[phase2_grid[k] for k in keys2]))
    results2 = []

    for i, vals in enumerate(combos2):
        params = {**best1, **dict(zip(keys2, vals))}
        # TP2 muss > TP1 sein
        if params["TP2_RR"] <= params["TP1_RR"]:
            continue
        sys.stdout.write(f"\r  [{i+1}/{len(combos2)}] TP1={vals[0]}, TP2={vals[1]}...")
        sys.stdout.flush()
        r = _test_params(params, symbols, start, train_end, balance)
        if "error" not in r:
            results2.append(r)

    results2 = [r for r in results2 if r.get("trades", 0) >= 10]
    results2.sort(key=lambda r: r["profit_factor"], reverse=True)
    print(f"\n\n  Phase 2 Top 5:")
    for i, r in enumerate(results2[:5], 1):
        _print_result(r, i)

    best2 = results2[0]["params"] if results2 else best1

    # ── Phase 3: Trailing-Feintuning ─────────────────────────
    print(f"\n  Phase 3: Trailing + Timing...")
    phase3_grid = {
        "TRAIL_ATR_MULTIPLIER": [0.5, 0.7, 1.0, 1.5],
        "TRAIL_ACTIVATION_RR": [0.5, 0.8, 1.0, 1.5],
        "TRAIL_STEP_PCT": [0.2, 0.3, 0.5],
    }
    keys3 = list(phase3_grid.keys())
    combos3 = list(itertools.product(*[phase3_grid[k] for k in keys3]))
    results3 = []

    for i, vals in enumerate(combos3):
        params = {**best2, **dict(zip(keys3, vals))}
        sys.stdout.write(f"\r  [{i+1}/{len(combos3)}] Trail={vals[0]}, Act={vals[1]}, Step={vals[2]}...")
        sys.stdout.flush()
        r = _test_params(params, symbols, start, train_end, balance)
        if "error" not in r:
            results3.append(r)

    results3 = [r for r in results3 if r.get("trades", 0) >= 10]
    results3.sort(key=lambda r: r["profit_factor"], reverse=True)
    print(f"\n\n  Phase 3 Top 5:")
    for i, r in enumerate(results3[:5], 1):
        _print_result(r, i)

    best3 = results3[0]["params"] if results3 else best2

    # ── Phase 4: Time-Exit Tuning ────────────────────────────
    print(f"\n  Phase 4: Time-Exits...")
    phase4_grid = {
        "MAX_TRADE_HOURS": [12, 24, 48],
        "STALE_TRADE_HOURS": [36, 48, 72],
    }
    keys4 = list(phase4_grid.keys())
    combos4 = list(itertools.product(*[phase4_grid[k] for k in keys4]))
    results4 = []

    for i, vals in enumerate(combos4):
        params = {**best3, **dict(zip(keys4, vals))}
        if params["STALE_TRADE_HOURS"] <= params["MAX_TRADE_HOURS"]:
            continue
        sys.stdout.write(f"\r  [{i+1}/{len(combos4)}] MaxH={vals[0]}, StaleH={vals[1]}...")
        sys.stdout.flush()
        r = _test_params(params, symbols, start, train_end, balance)
        if "error" not in r:
            results4.append(r)

    results4 = [r for r in results4 if r.get("trades", 0) >= 10]
    results4.sort(key=lambda r: r["profit_factor"], reverse=True)
    print(f"\n\n  Phase 4 Top 3:")
    for i, r in enumerate(results4[:3], 1):
        _print_result(r, i)

    # Bestes Gesamtergebnis aus allen Phasen
    all_valid = [r for phase in [results, results2, results3, results4]
                 for r in phase if r.get("trades", 0) >= 10]
    all_valid.sort(key=lambda r: r["profit_factor"], reverse=True)
    best_final = all_valid[0] if all_valid else {"params": best3, "error": "Kein profitables Ergebnis"}

    # ── Phase 5: Out-of-Sample Validierung ────────────────────
    oos_result = None
    if validate and test_start:
        print(f"\n  Phase 5: Out-of-Sample Validierung ({test_start} -> {end})...")
        oos_result = _test_params(best_final["params"], symbols, test_start, end, balance)
        if "error" not in oos_result:
            print(f"\n  OOS-Ergebnis (ungesehene Daten):")
            _print_result(oos_result)
            # Warnung bei starkem Overfitting
            train_pf = best_final.get("profit_factor", 0)
            oos_pf = oos_result.get("profit_factor", 0)
            if train_pf > 0 and oos_pf > 0:
                degradation = (train_pf - oos_pf) / train_pf * 100
                if degradation > 50:
                    print(f"\n  WARNUNG: Starkes Overfitting! Train-PF={train_pf:.2f} -> OOS-PF={oos_pf:.2f} ({degradation:.0f}% Degradation)")
                elif degradation > 20:
                    print(f"\n  HINWEIS: Moderates Overfitting ({degradation:.0f}% Degradation)")
                else:
                    print(f"\n  ROBUST: OOS-Degradation nur {degradation:.0f}% -- Parameter generalisieren gut!")
        else:
            print(f"\n  OOS-Fehler: {oos_result.get('error', 'unbekannt')}")

    # ── Zusammenfassung ──────────────────────────────────────
    print(f"\n{'='*65}")
    print(f"  OPTIMALE PARAMETER:")
    print(f"{'='*65}")
    for k, v in best_final["params"].items():
        print(f"  {k:30s} = {v}")
    print(f"\n  Train-Ergebnis:")
    _print_result(best_final)
    if oos_result and "error" not in oos_result:
        print(f"\n  OOS-Ergebnis:")
        _print_result(oos_result)
    print(f"{'='*65}")

    return best_final


if __name__ == "__main__":
    result = optimize(
        start="2025-01-01",
        balance=1000.0,
    )
