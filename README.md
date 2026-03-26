# AI Trading Bot

Professzionális multi-indicator momentum trading bot Python alapon.

## Stratégia

**Multi-Indicator Momentum + Mean Reversion**

Minden trade-hez **minimum 4 feltételnek** kell teljesülnie egyszerre:

| # | Feltétel | Indikátor | Cél |
|---|----------|-----------|-----|
| 1 | Trend alignment | EMA 9/21/50 | Csak a trend irányában kereskedünk |
| 2 | Momentum | RSI(14) 45–70 | Bullish, de nem túlvett |
| 3 | Confirmation | MACD histogram | Pozitív és növekvő |
| 4 | Entry timing | Bollinger / EMA21 | Pullback a trendbe |
| 5 | Volume | 20-bar MA | Volumen spike megerősíti a mozgást |

### Kockázatkezelés

- **Max 1.5% kockázat** per trade (tőke arányosan)
- **ATR-alapú stop-loss** (1.5× ATR az entry alatt/felett)
- **2.5:1 risk/reward** arány (take-profit)
- **Trailing stop** aktiválódik +1R gain után
- **Max 5% napi veszteség** — onnantól a bot leáll aznap
- **Max 15% drawdown** circuit breaker
- **Max 3 pozíció** egyszerre

## Telepítés

```bash
pip install -r requirements.txt
cp .env.example .env
# Szerkeszd a .env fájlt és add meg az API kulcsaidat
```

## Használat

```bash
# Backtest (historikus adatokon)
python bot.py --backtest

# Paper trading (valódi számok, de nem küld valódi ordereket)
python bot.py --paper

# Éles kereskedés (TESTNET=True legyen a config.py-ban először!)
python bot.py
```

## Konfiguráció

Minden beállítás a `config.py`-ban van. Legfontosabbak:

```python
TESTNET = True          # Mindig True-val kezdj!
SYMBOLS = [...]         # Milyen párokat kereskedjen
RISK_PER_TRADE = 0.015  # 1.5% kockázat per trade
INITIAL_CAPITAL = 1000  # Induló tőke (USD)
```

## FONTOS figyelmeztetés

> A közösségi médián terjedő "48 óra alatt 10× profit" posztok **99%-ban fake-ek vagy scam-ek**.
> A valódi kereskedés kockázatos. Soha ne kockáztass többet, mint amennyit elveszíthetsz.
> Mindig **tesztneten** kezdj, majd forward-teszteld papír-kereskedéssel, mielőtt valódi pénzt teszel bele.

## Fájlstruktúra

```
├── bot.py           — Fő loop, belépési pont
├── strategy.py      — Technikai elemzés és jelzések
├── risk_manager.py  — Pozícióméretezés, stop-loss, drawdown
├── exchange.py      — CCXT exchange connector
├── backtester.py    — Historikus backtest
├── config.py        — Minden beállítás egy helyen
└── requirements.txt
```
