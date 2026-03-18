# AIvestor — Professioneller Krypto-Trading-Bot

> Regelbasierter, vollautomatischer Trading-Bot für Binance.
> Multi-Symbol · Multi-Timeframe · Score-System · Trailing Stop · Partial Take-Profit

---

## Inhaltsverzeichnis

1. [Überblick](#überblick)
2. [Features](#features)
3. [Strategie](#strategie)
4. [Architektur](#architektur)
5. [Installation](#installation)
6. [Konfiguration](#konfiguration)
7. [API Keys einrichten](#api-keys-einrichten)
8. [Bot starten](#bot-starten)
9. [Signal-System](#signal-system)
10. [Risiko-Management](#risiko-management)
11. [Markt-Regime](#markt-regime)
12. [Korrelations-Schutz](#korrelations-schutz)
13. [Backtesting & Optimierung](#backtesting--optimierung)
14. [Dateistruktur](#dateistruktur)
15. [Realistische Erwartungen](#realistische-erwartungen)
16. [Sicherheitshinweise](#sicherheitshinweise)

---

## Überblick

AIvestor ist ein vollautomatischer Trading-Bot für Binance, der auf einem regelbasierten, datengetriebenen Ansatz basiert. Er analysiert **8 Krypto-Paare** gleichzeitig auf **3 Zeitebenen** (4H, 1H, 15m) und handelt nur dann, wenn ein klares, mehrdimensionales Signal vorliegt.

### Kernprinzipien

- **Kein Gambling** — Trade nur wenn mindestens 8 von 12 möglichen Punkten erreicht
- **Kapitalerhalt zuerst** — Trailing Stop und Partial-TP sichern Gewinne
- **Marktbewusstsein** — BTC-Regime bestimmt ob überhaupt gehandelt wird
- **Keine Korrelationsfallen** — Nie zwei stark korrelierte Coins gleichzeitig

---

## Features

| Feature | Beschreibung |
|---------|--------------|
| **Multi-Symbol** | 8 Paare gleichzeitig: BTC, ETH, BNB, SOL, AVAX, LINK, XRP, DOT |
| **Multi-Timeframe** | 4H Trend + 1H Struktur + 15m Entry-Präzision |
| **Score-System** | 0–12 Punkte, mindestens 8 zum Traden |
| **Markt-Regime** | BTC als Marktbarometer (BULL / BEAR / NEUTRAL) |
| **Korrelations-Schutz** | Gruppierung, max. 1 Trade pro Gruppe |
| **Partial Take-Profit** | TP1 bei 2:1 schließt 50%, TP2 bei 4:1 schließt Rest |
| **Trailing Stop-Loss** | SL zieht automatisch mit dem Preis mit |
| **Breakeven** | Nach TP1 wird SL auf Einstiegspreis gesetzt |
| **Server-Side Stop-Loss** | Nach TP1: SL-Order direkt bei Binance (Flash-Crash-Schutz) |
| **OCO-Schutz** | Race-Condition-sichere OCO-Verwaltung, kein doppelter Verkauf |
| **Dynamische Positionsgröße** | Normal 1%, High-Confidence 1.5% Risiko |
| **Trade-Log** | Jede Entscheidung wird in `trades_log.json` dokumentiert |
| **Backtesting** | Walk-Forward-Simulation auf historischen Daten mit Fees und Slippage |
| **Parameter-Optimizer** | 4-Phasen-Optimierung (Grob → Fein → Timing → Validierung) |
| **Risk-Manager** | Drawdown-Circuit-Breaker, Kelly-Criterion Positionsgröße |
| **Testnet-Modus** | Vollständiges Testen ohne echtes Geld |

---

## Strategie

### Philosophie

Der Bot folgt dem Ansatz eines professionellen Traders: **Warten auf die perfekte Gelegenheit** statt aggressiv zu handeln. Viele NO TRADE Signale sind ein Zeichen, dass der Bot korrekt arbeitet.

```
Kein Signal = kein Trade = kein Verlust
```

### Zeitebenen-Logik

```
4H-Chart  →  Übergeordneter Trend
              "In welche Richtung bewegt sich der Markt?"

1H-Chart  →  Marktstruktur
              "Bestätigt die Stundenchart den Trend?"

15m-Chart →  Präziser Entry
              "Wann genau einsteigen?"
```

Alle drei Ebenen müssen übereinstimmen — erst dann wird ein Entry erwogen.

### Momentum-Breakout

```
Bedingung:
  ✓ 4H EMA-Ausrichtung bullish (9 > 21 > 50)
  ✓ 1H Struktur bestätigt
  ✓ 15m EMA bullish aligned
  ✓ RSI steigt aus überverkauftem Bereich
  ✓ MACD bullish Crossover
  ✓ Volume mindestens 1.5x über Durchschnitt

Ergebnis: BUY Signal mit Score ≥ 8
```

### Gewinnmitnahme-Strategie

```
Entry bei $100

TP1 bei $104 (2:1 CRV)
  → 50% der Position verkaufen
  → Stop-Loss auf Breakeven ($100) setzen
  → Ab hier: kein Verlust mehr möglich

TP2 bei $108 (4:1 CRV)
  → Restliche 50% verkaufen
  → Position komplett geschlossen

Falls Preis fällt:
  → Trailing Stop schließt Position automatisch
  → Verlust max. 1% des Kontos
```

---

## Architektur

```
┌─────────────────────────────────────────────────────┐
│                      bot.py                          │
│              (Haupt-Kontrollschleife)                │
└──────┬──────────┬──────────────┬────────────────────┘
       │          │              │
       ▼          ▼              ▼
┌──────────┐ ┌─────────┐ ┌──────────────┐
│  market  │ │ signal  │ │   order      │
│  regime  │ │ engine  │ │  executor    │
│  .py     │ │  .py    │ │   .py        │
└──────────┘ └────┬────┘ └──────┬───────┘
                  │             │
       ┌──────────┼─────┐       │
       ▼          ▼     ▼       ▼
┌──────────┐ ┌──────┐ ┌──────┐ ┌──────────┐
│   data   │ │indic │ │ pos  │ │ exchange │
│ fetcher  │ │ators │ │ mgr  │ │   .py    │
│  .py     │ │ .py  │ │ .py  │ │          │
└──────────┘ └──────┘ └──────┘ └──────────┘
       │                               │
       └───────────────────────────────┘
                 Binance API
```

### Datenfluss pro Zyklus (60 Sekunden)

```
1. Markt-Regime prüfen (BTC 4H)
2. Offene Positionen verwalten:
   a. Aktuellen Preis holen
   b. Trailing Stop aktualisieren
   c. TP1/TP2/SL Check → automatisch ausführen
3. Neue Signale suchen:
   a. Für jedes Symbol: 4H, 1H, 15m Daten holen
   b. Indikatoren berechnen
   c. Score-System anwenden
   d. Korrelations-Check
   e. Regime-Filter
   f. Bei Score ≥ 8: Order platzieren
```

---

## Installation

### Voraussetzungen

- Python 3.10 oder höher
- pip
- Binance-Account (für Testnet kostenlos, kein KYC nötig)

### Schritt 1: Repository klonen

```bash
git clone https://github.com/BillysBj/AIvestor.git
cd AIvestor
```

### Schritt 2: Abhängigkeiten installieren

```bash
pip install -r requirements.txt
```

**Installierte Pakete:**

| Paket | Zweck |
|-------|-------|
| `python-binance` | Binance API Client |
| `pandas` | Datenverarbeitung |
| `pandas-ta` | Technische Indikatoren (EMA, RSI, MACD, ATR) |
| `requests` | HTTP-Anfragen |
| `colorama` | Farbige Terminal-Ausgabe |
| `python-dotenv` | Umgebungsvariablen aus `.env` |
| `pytest` | Unit-Tests (Entwicklung) |

### Schritt 3: Umgebungsvariablen konfigurieren

```bash
cp .env.example .env
```

Dann `.env` mit deinen API Keys befüllen (siehe [API Keys einrichten](#api-keys-einrichten)).

---

## Konfiguration

Alle Einstellungen befinden sich in `config.py`.

### Symbole und Gruppen

```python
SYMBOL_GROUPS = {
    "A": ["BTCUSDT", "ETHUSDT", "BNBUSDT"],    # Stark korreliert
    "B": ["SOLUSDT", "AVAXUSDT", "LINKUSDT"],   # Mittel korreliert
    "C": ["XRPUSDT", "DOTUSDT"],                # Eigene Dynamik
}
```

Eigene Symbole einfach in die passende Gruppe einfügen. Binance USDT-Pairs werden unterstützt.

### Risiko-Parameter

```python
ACCOUNT_RISK_BASE  = 1.0   # % des Kontos pro Trade (normal)
ACCOUNT_RISK_HIGH  = 1.5   # % des Kontos (bei High-Confidence Signal)
MAX_TRADE_USDT     = 100.0 # Absolutes Maximum pro Trade in USDT
MAX_OPEN_POSITIONS = 3     # Max. gleichzeitige Positionen
MAX_PER_GROUP      = 1     # Max. 1 Trade pro Korrelations-Gruppe
```

### Signal-Schwellenwerte

```python
MIN_SCORE       = 8    # Mindest-Score für einen Trade (von 12) — optimiert via Backtest
HIGH_CONF_SCORE = 10   # "Starkes" Signal → größere Position
MIN_CRV         = 2.0  # Mindest Chance-Risiko-Verhältnis (2:1)
```

### Take-Profit und Stop-Loss

```python
SL_ATR_MULTIPLIER    = 1.0  # SL = Preis ± (1.0 × ATR) — engerer SL, optimiert
TRAIL_ATR_MULTIPLIER = 1.5  # Trailing SL = Preis - (1.5 × ATR), optimiert
TP1_RR               = 2.0  # TP1 bei 2:1 → 50% schließen
TP2_RR               = 4.0  # TP2 bei 4:1 → Rest schließen
```

### Zeitbasierte Exits und Trailing

```python
MAX_TRADE_HOURS     = 48   # Breakeven-Exit falls TP1 nicht erreicht — optimiert
STALE_TRADE_HOURS   = 72   # Force-Close nach 72h — optimiert
TRAIL_STEP_PCT      = 0.5  # SL in 0.5%-Stufen nachziehen — optimiert
TRAIL_ACTIVATION_RR = 1.5  # Trailing erst nach 1.5:1 R:R — optimiert
```

### Umgebungsvariablen (.env)

```env
BINANCE_API_KEY=dein_api_key
BINANCE_API_SECRET=dein_api_secret
TRADING_MODE=testnet          # "testnet" oder "live"
ACCOUNT_RISK_PERCENT=1.0      # Überschreibt config.py
MAX_TRADE_USDT=100.0          # Sicherheitslimit
```

---

## API Keys einrichten

### Option A: Testnet (empfohlen zum Starten)

Kein echtes Geld, volles Funktionstest.

1. Gehe zu [testnet.binance.vision](https://testnet.binance.vision/)
2. Mit GitHub anmelden
3. **"Generate HMAC_SHA256 Key"** klicken
4. API Key und Secret in `.env` eintragen
5. `TRADING_MODE=testnet` setzen

Das Testnet-Konto wird automatisch mit Test-USDT befüllt.

### Option B: Live-Trading

> **Achtung:** Echtes Geld. Nur nach ausgiebigem Testnet-Testing.

1. Gehe zu [binance.com](https://binance.com) → Profil → API Management
2. Neuen API Key erstellen
3. Berechtigungen setzen:
   - ✅ Spot & Margin Trading aktivieren
   - ✅ IP-Whitelist einrichten (empfohlen)
   - ❌ Withdrawals **nicht** aktivieren
4. `.env` befüllen und `TRADING_MODE=live` setzen

**Sicherheitsregel:** API Keys niemals mit anderen teilen. Die `.env` Datei ist im `.gitignore` — sie wird nie in Git hochgeladen.

---

## Bot starten

### Testnet starten

```bash
python bot.py
```

### Live starten

```bash
# .env: TRADING_MODE=live
python bot.py
```

### Beispiel-Ausgabe

```
*****************************************************************
  TESTNET-MODUS — kein echtes Geld
  Symbole (8): BTCUSDT, ETHUSDT, BNBUSDT, SOLUSDT, ...
  Strategie: MTF (4H+1H+15m) | Min-Score: 8/12
  Max Positionen: 3 (max 1 pro Gruppe)
*****************************************************************

=================================================================
  TRADING BOT | TESTNET | 2026-03-18 14:30:00 UTC
  Markt-Regime: BULL | BTC bullish | EMA aufsteigend | RSI=52.3
  BTC: $74,240.00 | RSI: 52.3
  Offene Positionen: 1/3
=================================================================

  ETHUSDT [Gruppe A] | BUY | Score: 9/12 [*********...]
    Score 9/12 (HIGH) | CRV 2.1:1 | ATR=45.20
    Entry: $2,327.00 | SL: $2,259.20 | TP1: $2,462.60 | TP2: $2,598.20

  Öffne Long: ETHUSDT...
  [OK] Entry $2,327.00 | Qty 0.0215 | SL $2,259.20 | TP1 $2,462.60 | TP2 $2,598.20

  Nächste Analyse in 60s...
```

---

## Signal-System

### Score-Tabelle (max. 12 Punkte)

| Signal | Punkte | Beschreibung |
|--------|--------|--------------|
| **4H Trend-Alignment** | 2–3 | EMA 9>21>50 + 3 steigende Kerzen = 3 Punkte |
| **1H Struktur** | 0–2 | EMA-Ausrichtung + RSI in Range |
| **15m EMA-Alignment** | 0–2 | EMA 9>21>50 auf Entry-Timeframe |
| **RSI-Momentum** | 0–2 | RSI steigt aus überverkauft = 2 Punkte |
| **MACD-Crossover** | 0–2 | Frischer Crossover = 2, bereits drüber = 1 |
| **Volume-Bestätigung** | 0–1 | Volume ≥ 1.5x Durchschnitt |

### Entscheidungslogik

```
Score ≥ 10 →  HIGH-CONFIDENCE Trade (1.5% Risiko)
Score 8–9  →  NORMAL Trade (1.0% Risiko)
Score < 8  →  NO TRADE
```

### Chance-Risiko-Verhältnis (CRV)

Nur wenn CRV ≥ 2.0 (Gewinnziel mind. doppelt so groß wie Verlustrisiko):

```
Einstieg:  $100.00
Stop-Loss: $98.50  (-1.50$)  Risiko
TP1:       $103.00 (+3.00$)  2:1 CRV → 50% schließen
TP2:       $106.00 (+6.00$)  4:1 CRV → Rest schließen
```

---

## Risiko-Management

### Positionsgröße (dynamisch)

```
Risiko-USDT = Konto × Risiko%
Qty = Risiko-USDT / SL-Distanz

Beispiel ($1.000 Konto, BTC bei $74.000, SL bei $72.850):
  Risiko    = $1.000 × 1% = $10
  SL-Dist   = $74.000 - $72.850 = $1.150
  Qty       = $10 / $1.150 = 0.0087 BTC
  Notional  = 0.0087 × $74.000 = $643
```

### Trailing Stop

```
Nach Entry:
  SL = aktueller Preis - (1.5 × ATR)

Aktivierung: erst nach 1.5:1 R:R im Plus
Nachziehen: in 0.5%-Stufen (reduziert Whipsaw)

Bei jedem neuen Preishoch:
  Neuer SL = neues Hoch - (1.5 × ATR)
  (Nur wenn neuer SL > alter SL + 0.5%)

Nach TP1:
  SL = Entry-Preis (Breakeven)
  → Server-Side SL-Order bei Binance platziert
  → Trailing Stop zieht SL-Order automatisch nach
  → Ab hier kein Verlust mehr möglich
```

### Maximale Verlust-Szenarien

| Szenario | Auswirkung |
|----------|-----------|
| 1 Losing Trade | -1% des Kontos |
| 3 Losing Trades | -3% des Kontos |
| 10 Losing Trades in Folge | -10% des Kontos |
| TP1 erreicht, dann SL | 0% Verlust (Breakeven) |
| Flash Crash vor TP1 | OCO-Order greift bei Binance, Slippage möglich |
| Flash Crash nach TP1 | Server-Side SL-Order greift, kein Polling nötig |

---

## Markt-Regime

Der Bot analysiert **BTC auf dem 4H-Chart** als Barometer für den Gesamtmarkt.

### Regime-Typen

```
BULL  →  BTC EMA bullish ausgerichtet
          Preis über EMA 50
          RSI > 45
          → Longs erlaubt, keine Shorts

BEAR  →  BTC EMA bearish ausgerichtet
          Preis unter EMA 50
          RSI < 55
          → Keine Longs (Spot-only), Shorts möglich

NEUTRAL → Unklare Struktur
           → Sehr selektiv, nur High-Confidence Trades
```

### Warum das wichtig ist

80% aller Altcoins folgen BTC. Wenn BTC in einem Abwärtstrend ist und man ETH long kauft, verliert man fast immer. Der Regime-Filter verhindert diese Situation automatisch.

---

## Korrelations-Schutz

### Das Problem ohne Korrelations-Schutz

```
Ohne Schutz:  BTC long + ETH long + BNB long
              BTC fällt 5% → alle drei fallen 4-5%
              Gleichzeitiger Verlust auf 3 Positionen = -3% Konto
```

### Mit Korrelations-Gruppen

```python
Gruppe A: BTCUSDT, ETHUSDT, BNBUSDT   (stark korreliert)
Gruppe B: SOLUSDT, AVAXUSDT, LINKUSDT  (mittel korreliert)
Gruppe C: XRPUSDT, DOTUSDT             (eigene Dynamik)
```

**Regel:** Maximal 1 offene Position pro Gruppe.

```
Erlaubt:   ETH long (Gr. A) + SOL long (Gr. B) + XRP long (Gr. C)
           = 3 Positionen aus 3 verschiedenen Gruppen

Verboten:  BTC long + ETH long (beide Gruppe A)
           = zu hohes Korrelationsrisiko
```

---

## Backtesting & Optimierung

AIvestor enthält eine vollständige Backtesting-Engine und einen mehrstufigen Parameter-Optimizer, um die Strategie auf historischen Daten zu validieren und optimale Einstellungen zu finden.

### Backtester

```bash
python backtester.py                      # Standard-Backtest (alle Symbole)
python backtester.py --start 2024-01-01   # Ab bestimmtem Datum
python backtester.py --symbol BTCUSDT     # Einzelnes Symbol
```

Der Backtester simuliert die exakte Strategie auf historischen Klines-Daten:
- Download historischer Daten von Binance (mit lokalem Parquet-Cache)
- Walk-Forward-Simulation auf 15m-Kerzen
- Realistische Fees (0.10%) und Slippage (0.05%)
- Performance-Report mit Sharpe Ratio, Max Drawdown, Win-Rate

### Optimizer

```bash
python optimizer.py
```

4-Phasen-Optimierung:

| Phase | Parameter | Beschreibung |
|-------|-----------|--------------|
| 1 — Grob | SL_ATR, MIN_SCORE, TP1_RR, TP2_RR | Kernparameter breit scannen |
| 2 — Fein | TRAIL_ATR, TRAIL_STEP, TRAIL_ACTIVATION | Trailing-Stop feinjustieren |
| 3 — Timing | MAX_TRADE_HOURS, STALE_TRADE_HOURS | Zeitbasierte Exits optimieren |
| 4 — Validierung | Alle | Bester Parameter-Satz auf vollem Zeitraum testen |

### Optimierte Parameter (Backtest-Ergebnis)

Die folgenden Parameter wurden durch die 4-Phasen-Optimierung auf historischen Daten (8 Symbole, ab 2024-06-01) ermittelt und in `config.py` gesetzt:

| Parameter | Vorher | Optimiert | Auswirkung |
|-----------|--------|-----------|------------|
| `SL_ATR_MULTIPLIER` | 1.5 | **1.0** | Engerer SL, weniger Verlust pro Trade |
| `MIN_SCORE` | 7 | **8** | Weniger, aber qualitativ bessere Trades |
| `HIGH_CONF_SCORE` | 9 | **10** | Strengere High-Confidence-Schwelle |
| `TRAIL_ATR_MULTIPLIER` | 1.0 | **1.5** | Breiterer Trailing, weniger Whipsaw |
| `TRAIL_STEP_PCT` | 0.3 | **0.5** | Gröbere Stufen, weniger vorzeitige Exits |
| `TRAIL_ACTIVATION_RR` | 1.0 | **1.5** | Trailing erst bei stabilerem Profit |
| `MAX_TRADE_HOURS` | 24 | **48** | Mehr Zeit für TP1 |
| `STALE_TRADE_HOURS` | 48 | **72** | Weniger Force-Closes |

---

## Dateistruktur

```
AIvestor/
│
├── bot.py                # Hauptprogramm, Kontrollschleife
├── config.py             # Alle Einstellungen (inkl. optimierte Parameter)
│
├── signal_engine.py      # Multi-Timeframe Score-System
├── market_regime.py      # BTC-Regime Erkennung
├── indicators.py         # EMA, RSI, MACD, ATR Berechnung
│
├── data_fetcher.py       # Binance Marktdaten (parallel, kein API Key nötig)
├── exchange.py           # Binance Order-Ausführung (API Key nötig)
├── order_executor.py     # Long-Entry, Trailing-SL, Partial-TP, OCO-Management
├── position_manager.py   # Positions-Tracking (positions.json, atomare Writes)
│
├── risk_manager.py       # Drawdown-Circuit-Breaker, Kelly-Sizing, Trade-Stats
├── performance.py        # Performance-Tracking, tägliche P&L, Reports
├── logger.py             # Trade-Dokumentation (trades_log.json)
│
├── backtester.py         # Backtesting-Engine (Walk-Forward, Fees, Slippage)
├── optimizer.py          # 4-Phasen Parameter-Optimizer
│
├── main.py               # Legacy Entry-Point (→ bot.py)
├── requirements.txt      # Python-Abhängigkeiten
├── .env.example          # Vorlage für API Keys
├── .gitignore            # Schützt .env und Logs vor Git
│
└── tests/                # Unit-Tests (37 Tests)
    ├── conftest.py
    ├── test_signal_engine.py
    ├── test_position_manager.py
    └── test_risk_manager.py
```

### Automatisch erstellte Dateien (nicht in Git)

```
.env              # Deine API Keys (geheim!)
positions.json    # Aktuelle offene Positionen
trades_log.json   # Vollständige Trade-Historie
```

---

## Realistische Erwartungen

### Monatliche Projektion bei $1.000 Startkapital

| Szenario | Win-Rate | Trades | Ergebnis |
|----------|----------|--------|----------|
| Schlechter Markt | 40% | 10 | -$20 (-2%) |
| Normaler Markt | 52% | 35 | +$130 (+13%) |
| Guter Markt | 60% | 40 | +$280 (+28%) |

> Diese Zahlen sind **Schätzungen**, keine Garantien. Vergangene Performance garantiert keine zukünftigen Ergebnisse.

### Empfohlenes Vorgehen

```
Woche 1–2:  Testnet — Bot beobachten, Signale verstehen
Woche 3–4:  Live mit $50–100 — erste echte Erfahrungen
Monat 2+:   Live mit $500–1.000 — wenn Testnet profitabel war
```

### Tests

```bash
python -m pytest tests/ -v
```

37 Tests für Signal-Engine (Score-Berechnung, Signal-Generierung), Position-Manager (CRUD, Datenintegrität) und Risk-Manager (Drawdown-Limits, Kelly-Sizing, Trade-Stats).

### Was den Bot limitiert

- Handelt nur **Spot** (kein Futures, kein Hebel)
- Nur **Long-Positionen** — SELL-Signale werden erkannt, aber als NO TRADE behandelt
- Keine Nachrichten-Auswertung
- Backtesting und Optimizer verfügbar — Parameter wurden auf historischen Daten optimiert

---

## Sicherheitshinweise

> **Wichtig:** Automatisches Trading mit echtem Geld birgt erhebliches Verlustrisiko. Setze niemals mehr ein als du bereit bist zu verlieren.

### API-Key Sicherheit

- `.env` Datei niemals in Git committen (ist bereits in `.gitignore`)
- IP-Whitelist auf Binance einrichten
- **Withdrawals im API Key deaktivieren** — der Bot braucht sie nicht
- API Keys regelmäßig rotieren

### Bot-Überwachung

- Täglich kurz ins Terminal schauen
- Bei unerwartetem Verhalten: `Strg+C` → Bot stoppt sofort
- Offene Positionen sind in `positions.json` nachvollziehbar
- Alle Trades in `trades_log.json` dokumentiert

### Notfall-Schließung

Falls der Bot eine falsche Position hält:

```python
# In Python-Interpreter:
from order_executor import emergency_close
emergency_close("BTCUSDT")
```

Oder direkt auf Binance: Position manuell schließen — der Bot erkennt das beim nächsten Zyklus.

---

## Lizenz

MIT License — frei verwendbar, keine Garantie für Gewinne.

---

*AIvestor — Entwickelt mit professioneller Trading-Logik und konsequentem Risiko-Management.*
