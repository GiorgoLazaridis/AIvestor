"""
Professional Multi-Symbol Trading Bot
- Multi-Timeframe Analyse (4H Trend + 1H Struktur + 15m Entry)
- Markt-Regime Filter (BTC als Barometer)
- Korrelations-Schutz (max 1 Trade pro Symbol-Gruppe)
- Score-System 0–12 Punkte (mind. 7 zum Traden)
- Partial Take-Profit (TP1 bei 2:1, TP2 bei 4:1)
- Trailing Stop-Loss
"""
import sys
import time
from datetime import datetime, timezone
from colorama import init, Fore, Style
from binance.exceptions import BinanceAPIException

import config
import position_manager as pm
import order_executor as executor
import market_regime as regime_detector
from data_fetcher import fetch_all_timeframes, fetch_current_price
from indicators import calculate_all
from signal_engine import generate_signal
from logger import log_signal, log_event

init(autoreset=True)
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")


def _get_group(symbol: str) -> str | None:
    for grp, symbols in config.SYMBOL_GROUPS.items():
        if symbol in symbols:
            return grp
    return None


def _group_already_open(group: str) -> bool:
    """Prüft ob bereits eine Position aus dieser Korrelations-Gruppe offen ist."""
    all_pos = pm.load_all()
    for sym, pos in all_pos.items():
        if pos.active and _get_group(sym) == group:
            return True
    return False


def _header(regime):
    mode = f"{Fore.RED}LIVE{Style.RESET_ALL}" if not config.TESTNET else f"{Fore.YELLOW}TESTNET{Style.RESET_ALL}"
    ts   = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    regime_color = Fore.GREEN if regime.regime == "BULL" else (
                   Fore.RED   if regime.regime == "BEAR" else Fore.YELLOW)

    print(f"\n{Fore.CYAN}{'='*65}")
    print(f"  TRADING BOT | {mode} | {ts} UTC")
    print(f"  Markt-Regime: {regime_color}{regime.regime}{Style.RESET_ALL} | {regime.detail}")
    print(f"  BTC: ${regime.btc_price:,.2f} | RSI: {regime.btc_rsi}")
    print(f"  Offene Positionen: {pm.count_active()}/{config.MAX_OPEN_POSITIONS}")
    print(f"{'='*65}{Style.RESET_ALL}")


def _print_position(pos: pm.Position, price: float):
    pnl_open  = (price - pos.entry_price) * pos.quantity_remaining
    pnl_total = pos.pnl_realized + pnl_open
    c = Fore.GREEN if pnl_total >= 0 else Fore.RED
    tp1_done = f"{Fore.GREEN}[DONE]{Style.RESET_ALL}" if pos.tp1_hit else f"{Fore.YELLOW}[offen]{Style.RESET_ALL}"
    grp = _get_group(pos.symbol)

    print(f"\n  {Fore.CYAN}{pos.symbol}{Style.RESET_ALL} [Gruppe {grp}] | Score: {pos.score}/12 | {pos.confidence}")
    print(f"    Entry:    ${pos.entry_price:,.4f}  |  Qty: {pos.quantity_remaining}")
    print(f"    Trail-SL: ${pos.trailing_sl:,.4f}")
    print(f"    TP1 2:1:  ${pos.take_profit1:,.4f}  {tp1_done}")
    print(f"    TP2 4:1:  ${pos.take_profit2:,.4f}")
    print(f"    Jetzt:    ${price:,.4f}  |  P&L: {c}{pnl_total:+.2f} USDT{Style.RESET_ALL}")


def _print_signal(signal, skipped_reason=""):
    if signal.action == "BUY":
        c = Fore.GREEN
    elif signal.action == "SELL":
        c = Fore.RED
    else:
        c = Fore.WHITE

    bar = "*" * signal.score + "." * (12 - signal.score)
    grp = _get_group(signal.symbol)
    skip_note = f"  {Fore.YELLOW}[ÜBERSPRUNGEN: {skipped_reason}]{Style.RESET_ALL}" if skipped_reason else ""

    print(f"\n  {c}{signal.symbol}{Style.RESET_ALL} [Gruppe {grp}] | {signal.action} | Score: {signal.score}/12 [{bar}]")
    print(f"    {signal.reason}{skip_note}")
    if signal.action != "NO TRADE" and not skipped_reason:
        print(f"    Entry: ${signal.entry:,.4f} | SL: ${signal.stop_loss:,.4f}")
        print(f"    TP1:   ${signal.take_profit1:,.4f} | TP2: ${signal.take_profit2:,.4f}")


def run():
    if config.TESTNET:
        print(f"\n{Fore.YELLOW}{'*'*65}")
        print(f"  TESTNET-MODUS — kein echtes Geld")
        print(f"  Symbole ({len(config.SYMBOLS)}): {', '.join(config.SYMBOLS)}")
        print(f"  Gruppen: A={config.SYMBOL_GROUPS['A']} | B={config.SYMBOL_GROUPS['B']} | C={config.SYMBOL_GROUPS['C']}")
        print(f"  Strategie: MTF (4H+1H+15m) | Min-Score: {config.MIN_SCORE}/12")
        print(f"  Max Positionen: {config.MAX_OPEN_POSITIONS} (max {config.MAX_PER_GROUP} pro Gruppe)")
        print(f"{'*'*65}{Style.RESET_ALL}\n")
    else:
        print(f"\n{Fore.RED}{'!'*65}")
        print(f"  LIVE-MODUS | ECHTES GELD | Max ${config.MAX_TRADE_USDT}/Trade")
        print(f"{'!'*65}{Style.RESET_ALL}\n")

    print("  Bot läuft. Strg+C zum Beenden.\n")

    while True:
        try:
            # ── Markt-Regime prüfen ───────────────────────────────
            regime = regime_detector.detect()
            _header(regime)

            # ── Offene Positionen verwalten ───────────────────────
            all_pos = pm.load_all()
            for symbol, pos in list(all_pos.items()):
                if not pos.active:
                    continue
                try:
                    price = fetch_current_price(symbol)
                    pos   = executor.update_trailing_stop(pos, price)
                    pos, event = executor.check_and_handle_exits(pos, price)

                    if event:
                        print(f"\n  {Fore.MAGENTA}[EXIT] {symbol}: {event}{Style.RESET_ALL}")
                        log_event(symbol, "EXIT", event)
                    else:
                        _print_position(pos, price)

                except Exception as e:
                    print(f"  {Fore.RED}Fehler bei {symbol}: {e}{Style.RESET_ALL}")

            # ── Neue Signale suchen ───────────────────────────────
            open_count = pm.count_active()
            if open_count >= config.MAX_OPEN_POSITIONS:
                print(f"\n  {Fore.YELLOW}Max. Positionen ({open_count}/{config.MAX_OPEN_POSITIONS}) — kein neuer Entry.{Style.RESET_ALL}")
            elif not regime.allow_longs and not regime.allow_shorts:
                print(f"\n  {Fore.YELLOW}Markt-Regime NEUTRAL — kein Trade.{Style.RESET_ALL}")
            else:
                print(f"\n  Analysiere {len(config.SYMBOLS)} Symbole...")

                for symbol in config.SYMBOLS:
                    if pm.load(symbol).active:
                        continue
                    if pm.count_active() >= config.MAX_OPEN_POSITIONS:
                        break

                    # Korrelations-Check
                    grp = _get_group(symbol)
                    if grp and _group_already_open(grp):
                        print(f"  {Fore.YELLOW}{symbol}: Gruppe {grp} bereits im Markt — übersprungen{Style.RESET_ALL}")
                        continue

                    try:
                        dfs    = fetch_all_timeframes(symbol)
                        dfs    = {tf: calculate_all(df) for tf, df in dfs.items()}
                        signal = generate_signal(symbol, dfs)
                        log_signal(signal)

                        # Regime-Filter
                        skip = ""
                        if signal.action == "BUY" and not regime.allow_longs:
                            skip = f"Regime={regime.regime} erlaubt keine Longs"
                        elif signal.action == "SELL" and not regime.allow_shorts:
                            skip = f"Regime={regime.regime} erlaubt keine Shorts"

                        _print_signal(signal, skipped_reason=skip)

                        if signal.action == "BUY" and not skip:
                            print(f"\n  {Fore.GREEN}Öffne Long: {symbol}...{Style.RESET_ALL}")
                            pos = executor.open_long(signal)
                            msg = (f"Entry ${pos.entry_price:,.4f} | Qty {pos.quantity} | "
                                   f"SL ${pos.stop_loss:,.4f} | TP1 ${pos.take_profit1:,.4f} | "
                                   f"TP2 ${pos.take_profit2:,.4f}")
                            print(f"  {Fore.GREEN}[OK] {msg}{Style.RESET_ALL}")
                            log_event(symbol, "OPEN_LONG", msg)

                        elif signal.action == "SELL" and not skip:
                            print(f"  {Fore.YELLOW}{symbol}: SELL erkannt — Spot-only, kein Short.{Style.RESET_ALL}")

                    except BinanceAPIException as e:
                        print(f"  {Fore.RED}Binance API: {e.message}{Style.RESET_ALL}")
                    except ValueError as e:
                        print(f"  {Fore.RED}{symbol}: {e}{Style.RESET_ALL}")
                    except Exception as e:
                        print(f"  {Fore.RED}{symbol} Fehler: {e}{Style.RESET_ALL}")

        except KeyboardInterrupt:
            print(f"\n{Fore.YELLOW}Bot gestoppt.{Style.RESET_ALL}")
            sys.exit(0)
        except Exception as e:
            print(f"{Fore.RED}Kritischer Fehler: {e}{Style.RESET_ALL}")
            log_event("SYSTEM", "ERROR", str(e))

        print(f"\n  Nächste Analyse in {config.LOOP_INTERVAL_SECONDS}s...")
        time.sleep(config.LOOP_INTERVAL_SECONDS)


if __name__ == "__main__":
    run()
