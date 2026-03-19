# AIvestor Tutorial — Schritt fuer Schritt

> Dieses Tutorial erklaert dir alles, was du brauchst, um den Bot einzurichten,
> im Testnet zu testen und spaeter mit echtem Geld zu starten.
> Kein Vorwissen noetig — jeder Schritt wird erklaert.

---

## Inhaltsverzeichnis

1. [Was ist AIvestor?](#1-was-ist-aivestor)
2. [Voraussetzungen](#2-voraussetzungen)
3. [Installation](#3-installation)
4. [Testnet einrichten (kein echtes Geld)](#4-testnet-einrichten)
5. [Bot im Testnet starten](#5-bot-im-testnet-starten)
6. [Was der Bot macht (Ablauf verstehen)](#6-was-der-bot-macht)
7. [Backtesting — Strategie auf historischen Daten testen](#7-backtesting)
8. [Optimizer — Beste Parameter finden](#8-optimizer)
9. [Live-Trading mit echtem Geld](#9-live-trading)
10. [Ueberwachung und Reporting](#10-ueberwachung)
11. [Notfall: Position manuell schliessen](#11-notfall)
12. [Haeufige Fragen](#12-faq)

---

## 1. Was ist AIvestor?

AIvestor ist ein vollautomatischer Krypto-Trading-Bot fuer Binance. Er:

- Analysiert 8 Krypto-Paare gleichzeitig (BTC, ETH, BNB, SOL, AVAX, LINK, XRP, DOT)
- Nutzt 3 Zeitebenen (4H, 1H, 15m) fuer praezise Signale
- Handelt nur wenn ein starkes Signal vorliegt (Score >= 8 von 14)
- Sichert Gewinne automatisch (Partial Take-Profit, Trailing Stop)
- Schuetzt dein Kapital (Circuit Breaker, Server-Side Stop-Loss)

**Wichtig:** Der Bot handelt nur **Spot** (kein Hebel, kein Futures). Er kann nur **kaufen** (Long), nicht shorten. Das bedeutet: er verdient nur in steigenden Maerkten.

---

## 2. Voraussetzungen

Du brauchst:

- **Python 3.10+** — [python.org/downloads](https://python.org/downloads)
- **Git** — [git-scm.com](https://git-scm.com)
- **Binance-Account** — Fuer Testnet reicht ein GitHub-Account, fuer Live brauchst du KYC
- **Terminal/Kommandozeile** — CMD, PowerShell, oder Git Bash auf Windows

### Python pruefen

Oeffne ein Terminal und tippe:

```bash
python --version
```

Wenn du `Python 3.10` oder hoeher siehst, passt alles.

---

## 3. Installation

### 3.1 Repository klonen

```bash
git clone https://github.com/BillysBj/AIvestor.git
cd AIvestor
```

### 3.2 Abhaengigkeiten installieren

```bash
pip install -r requirements.txt
```

Das installiert alle benoetigten Pakete:
- `python-binance` — Verbindung zu Binance
- `pandas` + `pandas-ta` — Datenverarbeitung und Indikatoren
- `requests` — HTTP-Anfragen
- `colorama` — Farbige Terminal-Ausgabe
- `python-dotenv` — Umgebungsvariablen
- `pytest` — Tests
- `pyarrow` — Backtest-Daten-Cache

### 3.3 Umgebungsvariablen vorbereiten

Erstelle eine `.env` Datei im Projektordner:

```bash
cp .env.example .env
```

Falls `.env.example` nicht existiert, erstelle `.env` manuell mit diesem Inhalt:

```env
BINANCE_API_KEY=dein_api_key_hier
BINANCE_API_SECRET=dein_api_secret_hier
TRADING_MODE=testnet
```

**Die `.env` Datei wird NIEMALS in Git hochgeladen** (ist in `.gitignore`).

---

## 4. Testnet einrichten

Das Testnet ist eine Simulation von Binance mit Spielgeld. Perfekt zum Testen.

### 4.1 Testnet API-Key erstellen

1. Gehe zu [testnet.binance.vision](https://testnet.binance.vision/)
2. Klicke auf **"Log In with GitHub"** (kein Binance-Account noetig!)
3. Klicke auf **"Generate HMAC_SHA256 Key"**
4. Gib einen Namen ein (z.B. "AIvestor Test")
5. Du bekommst:
   - **API Key** — ein langer String (Beispiel: `abc123...`)
   - **Secret Key** — ein noch laengerer String

### 4.2 Keys in .env eintragen

Oeffne die `.env` Datei und trage die Keys ein:

```env
BINANCE_API_KEY=abc123dein_api_key_hier
BINANCE_API_SECRET=xyz789dein_secret_hier
TRADING_MODE=testnet
```

**Wichtig:**
- `TRADING_MODE=testnet` — damit der Bot das Testnet nutzt
- Die Keys sind NUR fuer das Testnet gueltig (nicht fuer echtes Geld)
- Das Testnet gibt dir automatisch Test-USDT zum Spielen

### 4.3 Pruefen ob es funktioniert

```bash
python -c "from exchange import get_client, get_balance_usdt; print(f'Balance: ${get_balance_usdt():,.2f}')"
```

Wenn du eine Zahl siehst (z.B. `Balance: $10,000.00`), ist alles korrekt eingerichtet.

---

## 5. Bot im Testnet starten

### 5.1 Bot starten

```bash
python bot.py
```

Du siehst jetzt etwas wie:

```
*****************************************************************
  TESTNET-MODUS — kein echtes Geld
  Symbole (8): BTCUSDT, ETHUSDT, BNBUSDT, SOLUSDT, ...
  Strategie: MTF (4H+1H+15m) | Min-Score: 8/14
  Max Positionen: 3 (max 1 pro Gruppe)
  Risk: Kelly=True | DD-Limit: 3.0%/Tag
*****************************************************************

  Bot laeuft. Strg+C zum Beenden.
```

### 5.2 Was passiert jetzt?

Der Bot macht alle 60 Sekunden einen Zyklus:

1. **BTC-Regime pruefen** — Ist der Markt bullish, bearish oder neutral?
2. **Offene Positionen verwalten** — Trailing Stop nachziehen, TP1/TP2 pruefen
3. **Neue Signale suchen** — Alle 8 Symbole analysieren

Wenn ein Signal stark genug ist (Score >= 8/14), kauft der Bot automatisch.

### 5.3 Bot beenden

Druecke **Strg+C**. Der Bot stoppt sauber und zeigt einen Performance-Report.

### 5.4 Was du im Testnet beobachten solltest

- Wie oft der Bot Trades oeffnet (sollte selektiv sein, nicht jede Minute)
- Wie die Positionen sich entwickeln (TP1 erreicht? Trailing Stop greift?)
- Ob der Circuit Breaker ausloest (nach 3% Tagesverlust pausiert der Bot)
- Die Trade-Historie in `trades_log.json`

**Empfehlung:** Lass den Bot mindestens 1-2 Wochen im Testnet laufen bevor du echtes Geld einsetzt.

---

## 6. Was der Bot macht

### 6.1 Signal-Generierung (Score 0-14)

Fuer jedes Symbol prueft der Bot 6 verschiedene Signale:

| Signal | Max Punkte | Was es prueft |
|--------|-----------|--------------|
| 4H Trend | 3 | Geht der uebergeordnete Trend nach oben? |
| ADX Trendstaerke | 2 | Ist der Trend STARK (nicht nur vorhanden)? |
| Pullback-Entry | 2 | Ist der Preis nahe am EMA (guter Einstieg)? |
| RSI Momentum | 2 | Beschleunigt der Preis? |
| MACD Crossover | 2 | Gibt es einen Momentum-Wechsel? |
| Volume Surge | 3 | Kaufen grosse Player gerade ein? |

**Nur wenn Score >= 8:** Bot eroeffnet eine Position.

### 6.2 Positionsverwaltung

Nach dem Kauf passiert automatisch:

```
1. Market BUY (volle Menge)
2. OCO-Order: TP1 (50% verkaufen bei 2:1 CRV) ODER Stop-Loss
3. Wenn TP1 erreicht:
   - 50% verkauft, Gewinn gesichert
   - Stop-Loss auf Breakeven (Einstiegspreis) gesetzt
   - Server-Side SL-Order bei Binance platziert
   - Ab hier: KEIN Verlust mehr moeglich
4. Trailing Stop zieht mit dem Preis nach oben
5. TP2 bei 4:1 CRV: Restliche 50% verkauft
```

### 6.3 Sicherheitsmechanismen

- **Circuit Breaker:** Nach 3% Tagesverlust pausiert der Bot bis zum naechsten Tag
- **Korrelations-Schutz:** Nie BTC und ETH gleichzeitig (bewegen sich fast identisch)
- **Max 3 Positionen:** Nicht mehr als 3 offene Trades gleichzeitig
- **Time-Exits:** Trades die nach 48h TP1 nicht erreichen werden bei Breakeven geschlossen
- **Server-Side SL:** Nach TP1 ist ein Stop-Loss direkt bei Binance hinterlegt (schuetzt auch wenn dein PC aus ist)

---

## 7. Backtesting

Der Backtester simuliert die Strategie auf historischen Daten. **Das ist der wichtigste Schritt** — damit siehst du, wie der Bot in der Vergangenheit performed haette.

### 7.1 Standard-Backtest (alle Symbole)

```bash
python backtester.py
```

Beim ersten Mal werden historische Daten von Binance heruntergeladen (kann ein paar Minuten dauern). Danach werden sie lokal gecacht.

### 7.2 Backtest mit bestimmtem Startdatum

```bash
python backtester.py --start 2024-01-01
```

### 7.3 Backtest fuer ein einzelnes Symbol

```bash
python backtester.py --symbol BTCUSDT --start 2025-01-01
```

### 7.4 Backtest mit anderem Startkapital

```bash
python backtester.py --balance 5000
```

### 7.5 Ergebnis lesen

Der Backtester zeigt am Ende einen Report:

```
============================================================
  BACKTEST ERGEBNIS
============================================================
  Startkapital:     $1,000.00
  Endkapital:       $1,093.07
  Gesamt-Return:    +9.31%
  Monatl. Schnitt:  +0.43%
  Max Drawdown:     2.06%
------------------------------------------------------------
  Trades:           311
  Gewinner:         137 (44.1%)
  Verlierer:        174
  Profit Factor:    1.64
  Sharpe Ratio:     1.13
============================================================
```

**Was die Zahlen bedeuten:**

| Metrik | Bedeutung | Gut wenn... |
|--------|-----------|-------------|
| **Profit Factor** | Gewinn / Verlust Verhaeltnis | > 1.0 (je hoeher desto besser) |
| **Gesamt-Return** | Gewinn in % | Positiv |
| **Max Drawdown** | Groesster Rueckgang vom Hoechststand | < 10% |
| **Win Rate** | Wie viel % der Trades profitabel | > 40% ist OK wenn Avg Win > Avg Loss |
| **Sharpe Ratio** | Risiko-adjustierter Return | > 1.0 ist gut |

### 7.6 Detaillierte Ergebnisse

Der Backtester speichert die Ergebnisse in `backtest_result.json`. Da findest du:
- Alle einzelnen Trades mit Entry/Exit-Preis und P&L
- Die Equity-Kurve (Kontostand ueber Zeit)

---

## 8. Optimizer

Der Optimizer testet systematisch verschiedene Parameter-Kombinationen und findet die profitabelste.

### 8.1 Optimizer starten

```bash
python optimizer.py
```

**Achtung:** Das dauert lange (1-3 Stunden)! Der Optimizer fuehrt ~90 Backtests durch.

### 8.2 Was der Optimizer macht

Er testet in 4 Phasen:

1. **Phase 1 — Grob:** SL-Weite und Min-Score
2. **Phase 2 — TP-Ratios:** Take-Profit-Levels
3. **Phase 3 — Trailing:** Trailing-Stop-Parameter
4. **Phase 4 — Timing:** Zeitbasierte Exits

Am Ende zeigt er die optimale Kombination.

### 8.3 Parameter anwenden

Die Ergebnisse des Optimizers musst du manuell in `config.py` eintragen. Die aktuellen Werte sind bereits das Ergebnis einer Optimierung.

---

## 9. Live-Trading mit echtem Geld

> **WARNUNG:** Trading mit echtem Geld birgt Verlustrisiko. Setze niemals mehr ein als du bereit bist komplett zu verlieren. Der Bot ist NICHT garantiert profitabel.

### 9.1 Voraussetzungen

- Mindestens 2 Wochen erfolgreicher Testnet-Betrieb
- Backtest-Ergebnisse geprueft und verstanden
- Binance-Account mit KYC-Verifizierung
- USDT auf dem Spot-Wallet

### 9.2 Binance API-Key erstellen (Live)

1. Gehe zu [binance.com](https://www.binance.com) -> Profil -> API Management
2. Erstelle einen neuen API Key
3. Setze die Berechtigungen:
   - **Spot & Margin Trading**: Aktivieren
   - **IP-Whitelist**: Empfohlen (nur deine IP)
   - **Withdrawals**: **NICHT aktivieren** (der Bot braucht das nicht!)
4. Speichere API Key und Secret

### 9.3 .env fuer Live-Modus anpassen

```env
BINANCE_API_KEY=dein_live_api_key
BINANCE_API_SECRET=dein_live_secret
TRADING_MODE=live
ACCOUNT_RISK_PERCENT=1.0
MAX_TRADE_USDT=100.0
```

**Erklaerung der Einstellungen:**

| Einstellung | Bedeutung | Empfehlung |
|-------------|-----------|------------|
| `TRADING_MODE=live` | Echtes Geld | Erst nach Testnet-Phase |
| `ACCOUNT_RISK_PERCENT=1.0` | 1% Risiko pro Trade | Nicht hoeher als 2% |
| `MAX_TRADE_USDT=100.0` | Max $100 pro Trade | Niedrig anfangen! |

### 9.4 Bot im Live-Modus starten

```bash
python bot.py
```

Du siehst jetzt:

```
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
  LIVE-MODUS | ECHTES GELD | Max $100/Trade
  DD-Limit: 3.0%/Tag | 6.0%/Woche
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
```

### 9.5 Empfohlenes Vorgehen

```
Woche 1-2:   Testnet — Bot beobachten, Signale verstehen
Woche 3-4:   Live mit $50-100 — erste echte Erfahrungen
Monat 2+:    Live mit $500-1.000 — wenn Testnet und erste Wochen profitabel
```

**Goldene Regel:** Beginne IMMER klein. Du kannst spaeter skalieren.

---

## 10. Ueberwachung und Reporting

### 10.1 Waehrend der Bot laeuft

Der Bot zeigt dir in jedem 60-Sekunden-Zyklus:

- **Markt-Regime** (BULL/BEAR/NEUTRAL)
- **Offene Positionen** mit aktuellem P&L
- **Neue Signale** mit Score-Details
- **Tages-P&L** und Kelly-Risk%

### 10.2 Trade-Log pruefen

Alle Trades werden in `trades_log.json` gespeichert:

```bash
python -c "import json; trades=json.load(open('trades_log.json')); print(f'{len(trades)} Eintraege'); [print(f\"  {t['timestamp'][:16]} {t['event']:8s} {t.get('symbol',''):10s} {t.get('action','')}\") for t in trades[-10:]]"
```

### 10.3 Positionen pruefen

Offene Positionen stehen in `positions.json`:

```bash
python -c "import json,os; p=json.load(open('positions.json')) if os.path.exists('positions.json') else {}; [print(f'  {s}: Entry=${d[\"entry_price\"]:,.2f} Qty={d[\"quantity_remaining\"]} TP1={\"DONE\" if d[\"tp1_hit\"] else \"offen\"}') for s,d in p.items() if d['active']] or print('  Keine offenen Positionen')"
```

### 10.4 Risk-Manager Status

```bash
python -c "import risk_manager as rm; s=rm.load_state(); stats=rm.get_trade_stats(s); print(f'Tages-P&L: {s.daily_pnl_usdt:+.2f} USDT'); print(f'Wochen-P&L: {s.weekly_pnl_usdt:+.2f} USDT'); print(f'Trades: {stats[\"trades\"]} | Win-Rate: {stats[\"win_rate\"]}% | Kelly: {stats[\"kelly_risk_pct\"]}%')"
```

---

## 11. Notfall: Position manuell schliessen

Falls etwas schiefgeht und du eine Position sofort schliessen willst:

### Option A: Ueber den Bot

```python
python -c "from order_executor import emergency_close; emergency_close('BTCUSDT')"
```

Ersetze `BTCUSDT` durch das Symbol das du schliessen willst.

### Option B: Direkt auf Binance

1. Gehe zu [binance.com](https://www.binance.com) -> Trade -> Spot
2. Waehle das entsprechende Paar
3. Verkaufe manuell per Market-Order

Der Bot erkennt beim naechsten Zyklus, dass die Position geschlossen wurde.

### Option C: Bot sofort stoppen

Druecke **Strg+C** im Terminal. Der Bot stoppt, aber offene Positionen bleiben auf Binance bestehen (OCO/SL-Orders sind server-side und bleiben aktiv).

---

## 12. Haeufige Fragen

### "Der Bot macht keine Trades"

Das ist normal! Der Bot ist absichtlich selektiv (Score >= 8/14). In ruhigen Maerkten oder bei schwachen Trends kann es Tage dauern bis ein Signal stark genug ist. **Das ist ein Feature, kein Bug.**

### "Kann ich die Symbole aendern?"

Ja, in `config.py`:

```python
SYMBOL_GROUPS = {
    "A": ["BTCUSDT", "ETHUSDT"],
    "B": ["SOLUSDT"],
}
```

Alle Symbole muessen Binance USDT-Paare sein.

### "Kann ich das Risiko aendern?"

Ja, in `.env`:

```env
ACCOUNT_RISK_PERCENT=0.5   # 0.5% statt 1% pro Trade (konservativer)
MAX_TRADE_USDT=50.0        # Max $50 pro Trade
```

Oder in `config.py` fuer mehr Kontrolle.

### "Der Circuit Breaker hat den Bot pausiert"

Das bedeutet du hast das Tages-Drawdown-Limit erreicht (Standard: 3%). Der Bot startet automatisch am naechsten Tag neu. Das ist ein **Schutzmechanismus** — er verhindert Tilt-Trading nach Verlusten.

### "Wie sicher sind meine API-Keys?"

- Die `.env` Datei ist in `.gitignore` und wird NIEMALS in Git hochgeladen
- Setze eine IP-Whitelist auf Binance
- Aktiviere NIEMALS Withdrawals im API-Key
- Rotiere deine Keys regelmaessig

### "Kann der Bot mein ganzes Geld verlieren?"

Theoretisch ja, aber die Sicherheitsmechanismen minimieren das Risiko erheblich:
- Max 1% Risiko pro Trade (konfigurierbar)
- Max 3 gleichzeitige Positionen
- Circuit Breaker bei 3% Tagesverlust
- Server-Side Stop-Loss nach TP1
- Korrelations-Schutz verhindert Cluster-Risiko

Bei einer katastrophalen Marktsituation (z.B. Exchange-Hack, Flash-Crash unter alle SL-Levels) kann es trotzdem zu hoeheren Verlusten kommen. **Investiere nur Geld das du verlieren kannst.**

### "Muss mein Computer die ganze Zeit laufen?"

Ja, der Bot laeuft lokal. Wenn dein PC aus ist, werden keine neuen Trades geoeffnet. **Aber:** Server-Side Stop-Loss-Orders und OCO-Orders sind bei Binance hinterlegt und bleiben aktiv, auch wenn dein PC aus ist. Bestehende Positionen sind also geschuetzt.

Fuer 24/7-Betrieb empfiehlt sich ein VPS (Virtual Private Server).

### "Was kostet der Bot?"

Der Bot selbst ist kostenlos (MIT License). Die einzigen Kosten sind:
- Binance Trading-Fees (0.1% pro Trade, 0.075% mit BNB)
- Optional: VPS fuer 24/7-Betrieb (~$5-10/Monat)

---

## Zusammenfassung: Schritt-fuer-Schritt Checkliste

- [ ] Python 3.10+ installiert
- [ ] Repository geklont
- [ ] `pip install -r requirements.txt` ausgefuehrt
- [ ] Testnet API-Keys erstellt
- [ ] `.env` Datei konfiguriert (`TRADING_MODE=testnet`)
- [ ] `python bot.py` gestartet und beobachtet
- [ ] Backtester laufen lassen (`python backtester.py`)
- [ ] Backtest-Ergebnisse verstanden
- [ ] Mindestens 2 Wochen Testnet erfolgreich
- [ ] Live API-Keys erstellt (IP-Whitelist, keine Withdrawals!)
- [ ] `.env` auf `TRADING_MODE=live` umgestellt
- [ ] Mit kleinem Betrag ($50-100) gestartet
- [ ] Taeglich kurz ins Terminal geschaut

---

*AIvestor — Datengetrieben, diszipliniert, automatisch.*
