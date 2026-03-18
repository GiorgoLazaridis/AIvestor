"""
Order-Ausführung mit:
- Dynamischer Positionsgröße (Score-basiert)
- Partial Take-Profit (TP1 = 50%, TP2 = 50%)
- Trailing Stop-Loss
"""
import math
from datetime import datetime, timezone
from binance.exceptions import BinanceAPIException

import config
import position_manager as pm
from signal_engine import Signal
from exchange import get_client, get_balance_usdt, get_symbol_info


def _round_step(value: float, step: float) -> float:
    precision = max(0, int(round(-math.log10(step))))
    return round(math.floor(value / step) * step, precision)


def _round_tick(value: float, tick: float) -> str:
    precision = max(0, int(round(-math.log10(tick))))
    return f"{round(math.floor(value / tick) * tick, precision):.{precision}f}"


def _calc_qty(symbol: str, entry: float, stop_loss: float, high_conf: bool) -> float:
    usdt = get_balance_usdt()
    risk_pct = config.ACCOUNT_RISK_HIGH if high_conf else config.ACCOUNT_RISK_BASE
    risk_usdt = usdt * (risk_pct / 100)
    risk_usdt = min(risk_usdt, config.MAX_TRADE_USDT * (risk_pct / 100))

    sl_dist = abs(entry - stop_loss)
    if sl_dist == 0:
        raise ValueError("SL-Distanz = 0")

    info = get_symbol_info(symbol)
    qty = _round_step(risk_usdt / sl_dist, info["step_size"])

    if qty * entry < info["min_notional"]:
        raise ValueError(f"Position zu klein: {qty} = ${qty*entry:.2f} (min ${info['min_notional']})")
    return qty


def open_long(signal: Signal) -> pm.Position:
    """
    Öffnet Long-Position:
    1. Market BUY (volle Qty)
    2. Limit-Sell bei TP1 (halbe Qty)
    3. Stop-Loss-Order für volle Qty (wird nach TP1 auf halbe reduziert)
    """
    client = get_client()
    info   = get_symbol_info(signal.symbol)
    high   = signal.confidence == "HIGH"
    qty    = _calc_qty(signal.symbol, signal.entry, signal.stop_loss, high)

    # Market Buy
    buy = client.order_market_buy(symbol=signal.symbol, quantity=qty)
    actual_entry = float(buy["fills"][0]["price"]) if buy.get("fills") else signal.entry
    order_id     = str(buy["orderId"])

    # Halbe Qty für TP1, halbe für TP2
    qty_tp1 = _round_step(qty * 0.5, info["step_size"])

    tp1 = _round_tick(signal.take_profit1, info["tick_size"])
    sl  = _round_tick(signal.stop_loss,    info["tick_size"])
    sl_limit = _round_tick(signal.stop_loss * 0.9995, info["tick_size"])

    # OCO für erste Hälfte (SL oder TP1)
    oco = client.create_oco_order(
        symbol=signal.symbol,
        side="SELL",
        quantity=qty_tp1,
        price=tp1,
        stopPrice=sl,
        stopLimitPrice=sl_limit,
        stopLimitTimeInForce="GTC"
    )

    pos = pm.Position(
        active=True,
        symbol=signal.symbol,
        side="BUY",
        entry_price=actual_entry,
        quantity=qty,
        quantity_remaining=qty,
        stop_loss=signal.stop_loss,
        trailing_sl=signal.stop_loss,
        take_profit1=signal.take_profit1,
        take_profit2=signal.take_profit2,
        atr=signal.atr,
        oco_order_id=str(oco["orderListId"]),
        entry_order_id=order_id,
        score=signal.score,
        confidence=signal.confidence,
        opened_at=datetime.now(timezone.utc).isoformat()
    )
    pm.save(signal.symbol, pos)
    return pos


def update_trailing_stop(pos: pm.Position, current_price: float) -> pm.Position:
    """
    Zieht den Trailing-Stop nach, wenn der Preis steigt.
    Neuer SL = Preis - (ATR * TRAIL_MULTIPLIER)
    """
    if not pos.active or pos.side != "BUY":
        return pos

    new_trail = current_price - (pos.atr * config.TRAIL_ATR_MULTIPLIER)
    if new_trail > pos.trailing_sl:
        pos.trailing_sl = round(new_trail, 2)
        pm.save(pos.symbol, pos)
    return pos


def check_and_handle_exits(pos: pm.Position, current_price: float) -> tuple[pm.Position, str]:
    """
    Prüft:
    1. Trailing-Stop getriggert?
    2. TP1 erreicht? → 50% schließen, SL auf Breakeven setzen
    3. TP2 erreicht? → Rest schließen
    Gibt (aktualisierte Position, Event-String) zurück.
    """
    client = get_client()
    info   = get_symbol_info(pos.symbol)

    # ── Trailing-Stop gecheckt ────────────────────────────────
    if current_price <= pos.trailing_sl and pos.active:
        _market_sell_remaining(client, pos, info)
        pnl = (pos.trailing_sl - pos.entry_price) * pos.quantity_remaining
        pos.pnl_realized += pnl
        pm.remove(pos.symbol)
        return pos, f"TRAILING_STOP (${pos.trailing_sl:,.2f}) | P&L={pnl:+.2f} USDT"

    # ── TP1 erreicht ─────────────────────────────────────────
    if not pos.tp1_hit and current_price >= pos.take_profit1:
        qty_close = _round_step(pos.quantity * 0.5, info["step_size"])
        client.order_market_sell(symbol=pos.symbol, quantity=qty_close)

        pnl = (current_price - pos.entry_price) * qty_close
        pos.pnl_realized += pnl
        pos.quantity_remaining -= qty_close
        pos.tp1_hit = True
        pos.trailing_sl = pos.entry_price  # SL auf Breakeven!
        pos.stop_loss   = pos.entry_price
        pm.save(pos.symbol, pos)
        return pos, f"TP1_HIT ({current_price:,.2f}) | +{pnl:.2f} USDT | SL auf Breakeven"

    # ── TP2 erreicht ─────────────────────────────────────────
    if pos.tp1_hit and current_price >= pos.take_profit2:
        _market_sell_remaining(client, pos, info)
        pnl = (current_price - pos.entry_price) * pos.quantity_remaining
        pos.pnl_realized += pnl
        pm.remove(pos.symbol)
        return pos, f"TP2_HIT ({current_price:,.2f}) | +{pnl:.2f} USDT | Position komplett geschlossen"

    return pos, ""


def _market_sell_remaining(client, pos: pm.Position, info: dict):
    qty = _round_step(pos.quantity_remaining, info["step_size"])
    if qty > 0:
        client.order_market_sell(symbol=pos.symbol, quantity=qty)


def emergency_close(symbol: str) -> None:
    """Notfall-Schließung per Market-Order."""
    pos = pm.load(symbol)
    if not pos.active:
        return
    client = get_client()
    info   = get_symbol_info(symbol)
    qty    = _round_step(pos.quantity_remaining, info["step_size"])
    if qty > 0:
        client.order_market_sell(symbol=symbol, quantity=qty)
    pm.remove(symbol)
