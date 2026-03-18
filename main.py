import time
import sys
import os
from datetime import datetime, timezone
from colorama import init, Fore, Style

import config
from data_fetcher import fetch_klines, fetch_current_price
from indicators import calculate_all
from signal_engine import generate_signal
from logger import log_signal

init(autoreset=True)
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")


def print_header():
    sep = "=" * 60
    print(f"\n{Fore.CYAN}{sep}")
    print(f"  TRADING-ALGORITHMUS  |  {config.SYMBOL}  |  {config.INTERVAL}")
    print(f"  {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print(f"{sep}{Style.RESET_ALL}")


def print_signal(signal, current_price: float):
    action = signal.action

    if action == "BUY":
        color = Fore.GREEN
    elif action == "SELL":
        color = Fore.RED
    else:
        color = Fore.YELLOW

    print(f"\n{color}{'-'*60}")
    print(f"  SIGNAL: {action}")
    print(f"{'-'*60}{Style.RESET_ALL}")

    if action != "NO TRADE":
        sl_pct = abs((signal.stop_loss - signal.entry) / signal.entry * 100)
        tp_pct = abs((signal.take_profit - signal.entry) / signal.entry * 100)

        print(f"  Entry:       ${signal.entry:,.2f}")
        print(f"  Stop-Loss:   ${signal.stop_loss:,.2f}  ({'-' if action == 'BUY' else '+'}{sl_pct:.2f}%)")
        print(f"  Take-Profit: ${signal.take_profit:,.2f}  ({'+' if action == 'BUY' else '-'}{tp_pct:.2f}%)")
        print(f"  CRV:         {signal.crv:.2f}:1")

    print(f"\n  {Fore.WHITE}Begründung:{Style.RESET_ALL}")
    print(f"  {signal.reason}")

    if signal.confirmed_signals:
        print(f"\n  {Fore.GREEN}Bestätigte Signale ({len(signal.confirmed_signals)}):{Style.RESET_ALL}")
        for s in signal.confirmed_signals:
            print(f"    [OK] {s}")

    if signal.rejected_signals:
        print(f"\n  {Fore.RED}Abgelehnte Signale:{Style.RESET_ALL}")
        for s in signal.rejected_signals:
            print(f"    [--] {s}")

    print(f"{color}{'-'*60}{Style.RESET_ALL}")


def run_once():
    """Einmaliger Analyse-Durchlauf."""
    print_header()

    print(f"  Lade Daten von Binance...")
    df = fetch_klines()
    df = calculate_all(df)

    current_price = fetch_current_price()
    print(f"  Aktueller Preis: ${current_price:,.2f}")

    signal = generate_signal(df)
    print_signal(signal, current_price)

    log_signal(signal, config.SYMBOL, config.INTERVAL)
    print(f"\n  {Fore.CYAN}Signal gespeichert in trades_log.json{Style.RESET_ALL}\n")

    return signal


def run_loop(interval_seconds: int = 60):
    """Dauerhafter Loop — analysiert jede `interval_seconds` Sekunden."""
    print(f"{Fore.CYAN}Starte kontinuierliche Analyse (alle {interval_seconds}s)...{Style.RESET_ALL}")
    print(f"  Beenden mit Strg+C\n")

    while True:
        try:
            run_once()
            print(f"  Warte {interval_seconds}s bis zur nächsten Analyse...")
            time.sleep(interval_seconds)
        except KeyboardInterrupt:
            print(f"\n{Fore.YELLOW}Analyse gestoppt.{Style.RESET_ALL}")
            sys.exit(0)
        except Exception as e:
            print(f"{Fore.RED}Fehler: {e}{Style.RESET_ALL}")
            print(f"  Retry in 30s...")
            time.sleep(30)


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "once"

    if mode == "loop":
        interval = int(sys.argv[2]) if len(sys.argv) > 2 else 60
        run_loop(interval)
    else:
        run_once()
