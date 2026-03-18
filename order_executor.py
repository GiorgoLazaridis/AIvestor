"""
Order-Ausführung mit:
- Dynamischer Positionsgröße (Score-basiert)
- Partial Take-Profit (TP1 = 50%, TP2 = 50%)
- Trailing Stop-Loss
- Server-Side Stop-Loss nach TP1
"""
import math
from datetime import datetime, timezone
from binance.exceptions import BinanceAPIException

import config
import position_manager as pm
from signal_engine import Signal
from exchange import get_client, get_balance_usdt, get_symbol_info
from logger import log_event


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


def _cancel_oco(client, symbol: str, oco_id: str) -> None:
    """Cancelt eine offene OCO-Order. Ignoriert Fehler wenn bereits geschlossen."""
    if not oco_id:
        return
    try:
        client.cancel_order_list(symbol=symbol, orderListId=int(oco_id))
    except BinanceAPIException as e:
        # -2011 = Order already filled/cancelled
        if e.code != -2011:
            raise


def _check_oco_status(client, symbol: str, oco_id: str) -> str | None:
    """
    Prüft den OCO-Status bei Binance.
    Returns: "TP1_FILLED", "SL_FILLED", oder None (noch offen/kein OCO).
    """
    if not oco_id:
        return None
    try:
        oco = client.get_order_list(orderListId=int(oco_id))
    except BinanceAPIException:
        return None

    if oco.get("listOrderStatus") != "ALL_DONE":
        return None

    # OCO hat 2 Orders: Limit (TP1) und Stop-Loss
    for order in oco.get("orders", []):
        order_detail = client.get_order(symbol=symbol, orderId=order["orderId"])
        if order_detail["status"] == "FILLED":
            if order_detail["type"] == "LIMIT_MAKER":
                return "TP1_FILLED"
            else:
                return "SL_FILLED"
    return None


def _cancel_order(client, symbol: str, order_id: str) -> None:
    """Cancelt eine einzelne Order. Ignoriert Fehler wenn bereits geschlossen."""
    if not order_id:
        return
    try:
        client.cancel_order(symbol=symbol, orderId=int(order_id))
    except BinanceAPIException as e:
        if e.code != -2011:
            raise


def _place_stop_loss_order(client, pos: pm.Position, info: dict) -> str:
    """
    Platziert eine Server-Side Stop-Loss-Limit-Order für die verbleibende Qty.
    Returns: orderId als String.
    """
    stop_price = _round_tick(pos.trailing_sl, info["tick_size"])
    # Limit etwas unter Stop für schnellere Ausführung
    limit_price = _round_tick(pos.trailing_sl * 0.9995, info["tick_size"])
    qty = _round_step(pos.quantity_remaining, info["step_size"])

    if qty <= 0:
        return ""

    order = client.create_order(
        symbol=pos.symbol,
        side="SELL",
        type="STOP_LOSS_LIMIT",
        timeInForce="GTC",
        quantity=qty,
        price=limit_price,
        stopPrice=stop_price,
    )
    return str(order["orderId"])


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
    Nach TP1: Server-Side SL-Order wird mitgezogen (nur bei >= 0.1% Differenz).
    """
    if not pos.active or pos.side != "BUY":
        return pos

    new_trail = current_price - (pos.atr * config.TRAIL_ATR_MULTIPLIER)
    if new_trail > pos.trailing_sl:
        old_trail = pos.trailing_sl
        pos.trailing_sl = round(new_trail, 2)

        # Server-Side SL nachziehen (nur nach TP1, nur bei >= 0.1% Bewegung)
        if pos.tp1_hit and pos.trailing_order_id:
            diff_pct = (pos.trailing_sl - old_trail) / old_trail if old_trail > 0 else 1
            if diff_pct >= 0.001:
                client = get_client()
                info = get_symbol_info(pos.symbol)
                _cancel_order(client, pos.symbol, pos.trailing_order_id)
                pos.trailing_order_id = _place_stop_loss_order(client, pos, info)

        pm.save(pos.symbol, pos)
    return pos


def check_and_handle_exits(pos: pm.Position, current_price: float) -> tuple[pm.Position, str]:
    """
    Prüft:
    0. OCO bei Binance bereits gefüllt? → registrieren OHNE nochmal zu verkaufen
    1. Trailing-Stop getriggert?
    2. TP1 erreicht? → OCO canceln, 50% schließen, SL auf Breakeven setzen
    3. TP2 erreicht? → Rest schließen
    Gibt (aktualisierte Position, Event-String) zurück.
    """
    client = get_client()
    info   = get_symbol_info(pos.symbol)

    # ── OCO-Status bei Binance prüfen (Race-Condition-Schutz) ─
    if not pos.tp1_hit and pos.oco_order_id:
        oco_result = _check_oco_status(client, pos.symbol, pos.oco_order_id)

        if oco_result == "TP1_FILLED":
            # OCO hat TP1 bereits ausgeführt — nur State aktualisieren
            qty_close = _round_step(pos.quantity * 0.5, info["step_size"])
            pnl = (pos.take_profit1 - pos.entry_price) * qty_close
            pos.pnl_realized += pnl
            pos.quantity_remaining -= qty_close
            pos.tp1_hit = True
            pos.trailing_sl = pos.entry_price
            pos.stop_loss   = pos.entry_price
            pos.oco_order_id = ""
            # Server-Side SL für verbleibende Qty
            pos.trailing_order_id = _place_stop_loss_order(client, pos, info)
            pm.save(pos.symbol, pos)
            return pos, f"TP1_HIT (OCO filled @ ~{pos.take_profit1:,.2f}) | +{pnl:.2f} USDT | SL auf Breakeven"

        elif oco_result == "SL_FILLED":
            # OCO hat SL bereits ausgeführt — Position schließen
            qty_close = _round_step(pos.quantity * 0.5, info["step_size"])
            pnl = (pos.stop_loss - pos.entry_price) * qty_close
            pos.pnl_realized += pnl
            pos.quantity_remaining -= qty_close
            pos.oco_order_id = ""
            # Restliche Qty per Market-Sell schließen
            if pos.quantity_remaining > 0:
                _market_sell_remaining(client, pos, info)
                pnl_rest = (current_price - pos.entry_price) * pos.quantity_remaining
                pos.pnl_realized += pnl_rest
            pm.remove(pos.symbol)
            return pos, f"SL_HIT (OCO filled @ ~{pos.stop_loss:,.2f}) | P&L={pos.pnl_realized:+.2f} USDT"

    # ── Trailing-Stop gecheckt ────────────────────────────────
    if current_price <= pos.trailing_sl and pos.active:
        _cancel_oco(client, pos.symbol, pos.oco_order_id)
        _cancel_order(client, pos.symbol, pos.trailing_order_id)
        _market_sell_remaining(client, pos, info)
        pnl = (pos.trailing_sl - pos.entry_price) * pos.quantity_remaining
        pos.pnl_realized += pnl
        pm.remove(pos.symbol)
        return pos, f"TRAILING_STOP (${pos.trailing_sl:,.2f}) | P&L={pnl:+.2f} USDT"

    # ── TP1 erreicht ─────────────────────────────────────────
    if not pos.tp1_hit and current_price >= pos.take_profit1:
        # OCO canceln BEVOR wir manuell verkaufen
        _cancel_oco(client, pos.symbol, pos.oco_order_id)

        qty_close = _round_step(pos.quantity * 0.5, info["step_size"])
        client.order_market_sell(symbol=pos.symbol, quantity=qty_close)

        pnl = (current_price - pos.entry_price) * qty_close
        pos.pnl_realized += pnl
        pos.quantity_remaining -= qty_close
        pos.tp1_hit = True
        pos.trailing_sl = pos.entry_price  # SL auf Breakeven!
        pos.stop_loss   = pos.entry_price
        pos.oco_order_id = ""
        # Server-Side SL für verbleibende Qty
        pos.trailing_order_id = _place_stop_loss_order(client, pos, info)
        pm.save(pos.symbol, pos)
        return pos, f"TP1_HIT ({current_price:,.2f}) | +{pnl:.2f} USDT | SL auf Breakeven"

    # ── TP2 erreicht ─────────────────────────────────────────
    if pos.tp1_hit and current_price >= pos.take_profit2:
        _cancel_oco(client, pos.symbol, pos.oco_order_id)
        _cancel_order(client, pos.symbol, pos.trailing_order_id)
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
    _cancel_oco(client, symbol, pos.oco_order_id)
    _cancel_order(client, symbol, pos.trailing_order_id)
    info   = get_symbol_info(symbol)
    qty    = _round_step(pos.quantity_remaining, info["step_size"])
    if qty > 0:
        client.order_market_sell(symbol=symbol, quantity=qty)
    pm.remove(symbol)
