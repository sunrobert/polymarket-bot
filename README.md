# polybot

**A modular paper-trading framework for Polymarket's recurring 5-minute Bitcoin "Up or Down" markets.** Plug in a strategy, point it at the live order book and a BTC oracle, and let it trade against real prices without real money.

> v1 is paper trading only. Live execution against the CLOB is deferred to v2.

---

## Why

Polymarket runs a `btc-up-or-down-5m` series — a new binary market every 5 minutes that resolves on Bitcoin's price direction. The markets are short, frequent, and the order book is public. That makes them a near-perfect sandbox for testing micro-strategies: hundreds of independent trades per day, fast feedback, and no need for capital until a strategy clears paper.

This repo provides the plumbing (feed, executor, portfolio, recorder) so a new strategy can be added in a single file and benchmarked against the same data the others saw.

---

## Tech Stack

| Layer | Tool |
|---|---|
| Language | Python 3.11+, `asyncio` |
| Config | `pydantic`, YAML |
| HTTP | `httpx` (async) |
| WebSocket | `websockets` |
| Money math | `decimal.Decimal` end-to-end |
| Testing | `pytest`, `pytest-asyncio` |
| Persistence | JSONL recordings (replayable) |
| External APIs | Polymarket Gamma + CLOB, Coinbase Exchange |

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                          External Sources                         │
│                                                                   │
│   Polymarket Gamma         Polymarket CLOB           Coinbase     │
│   (event discovery)         (order books)          (BTC oracle)   │
│      REST /events          REST + WebSocket       REST + WebSocket│
└──────────┬────────────────────────┬────────────────────────┬──────┘
           │                        │                        │
           ▼                        ▼                        ▼
┌──────────────────────────────────────────────────────────────────┐
│                           feed/live.py                            │
│  - Polls /events?series_slug=btc-up-or-down-5m every 15s          │
│  - Spawns one task per market within 10-min track horizon         │
│  - Subscribes to Up + Down books via CLOB WebSocket               │
│  - Defers Coinbase historical fetch until market start + 70s      │
│  - Emits MarketSnapshot on every book update + 1s heartbeat       │
└────────────────────────────────┬─────────────────────────────────┘
                                 │  MarketSnapshot
                                 ▼
┌──────────────────────────────────────────────────────────────────┐
│                            runner.py                              │
│                                                                   │
│   ┌────────────┐   ┌──────────────┐  ┌────────────┐  ┌─────────┐ │
│   │ Recorder   │   │  Strategy    │  │ Executor   │  │Portfolio│ │
│   │  (JSONL)   │ ◀─┤  .decide()   ├─▶│  .submit() ├─▶│ .apply()│ │
│   │  snapshots │   │  pure fn,    │  │  walks book│  │  P&L,   │ │
│   │  intents   │   │  no I/O      │  │  fills/sells│ │  positions│
│   │  fills     │   └──────────────┘  └────────────┘  │  halts  │ │
│   │  resolutions│                                    └─────────┘ │
│   └────────────┘                                                  │
└──────────────────────────────────────────────────────────────────┘
```

### Module Layout

```
src/polybot/
├── types.py              # Pure dataclasses: MarketSnapshot, TradeIntent, Fill, Position
├── config.py             # pydantic models + YAML loader
├── btc_feed.py           # Coinbase WS ticker + REST historical candles
├── feed/
│   ├── base.py           # Feed protocol
│   ├── live.py           # Live Polymarket feed (Gamma + CLOB)
│   └── historical.py     # Replay from JSONL recording
├── strategy/
│   ├── __init__.py       # make_strategy() factory
│   ├── bot1.py           # Late-window favorite buyer
│   ├── bot2_filter.py    # Bot 1 + BTC direction gate
│   ├── bot2_signal.py    # BTC-derived fair value vs market ask
│   ├── bot3_dipbuyer.py  # Mean-reversion entry + exit (Up side)
│   └── bot4_rallyfader.py # Pessimistic mirror of bot3 (Down side)
├── executor/
│   ├── base.py           # Executor protocol
│   └── paper.py          # Walks the in-memory book; synthetic bids for sells
├── portfolio.py          # Position tracking, P&L, kill switches
├── recorder.py           # Append-only JSONL writer
└── runner.py             # Wires feed → strategy → executor → portfolio
```

---

## Data Flow

Every strategy operates on the same input shape, regardless of source:

```python
MarketSnapshot(
    market_id="0xacdf...",           # condition ID
    timestamp=datetime(...),          # UTC
    time_to_resolve_s=12.4,           # seconds until market close
    up_token_id="78626...",
    down_token_id="57672...",
    up_best_ask=Decimal("0.92"),
    up_best_ask_size=Decimal("847"),
    down_best_ask=Decimal("0.10"),
    down_best_ask_size=Decimal("612"),
    up_asks=[BookLevel(price=..., size=...), ...],   # full ladder
    down_asks=[BookLevel(price=..., size=...), ...],
    btc_price=Decimal("82014.50"),    # latest Coinbase tick, None if no feed
    btc_open_price=Decimal("81949.03"), # BTC at event start, None if no feed
)
```

Strategies return zero or one `TradeIntent`:

```python
TradeIntent(
    intent_id="uuid-...",
    market_id="0xacdf...",
    side="up",           # "up" or "down"
    notional_usdc=Decimal("5.00"),
    action="buy",        # "buy" or "sell"
    shares=None,         # required for sells; close full position if None
)
```

The runner records every snapshot, intent, fill, and resolution to JSONL so a session can be replayed deterministically through any strategy.

---

## Strategies

| Bot | Mechanic | BTC feed? | Status |
|---|---|---|---|
| `bot1` | Buy heavy favorites ($0.85–$0.99) in the last 1–20s. No external signal. | No | Baseline — net negative in paper |
| `bot2_filter` | Bot 1 + only fire if BTC direction agrees with the in-band side. | Yes | Inherits Bot 1's no-edge profile |
| `bot2_signal` | Compute fair `p(up wins)` from BTC move + time-to-close (normal CDF); trade when fair value disagrees with market ask by `min_edge`. | Yes | Net negative at current σ |
| `bot3_dipbuyer` | Enter Up when ask ≤ $0.35, exit when implied bid ≥ $0.55. Mean-reversion / overreaction-bounce play. | No | Active testing |
| `bot4_rallyfader` | Pessimistic mirror of Bot 3. Enter Down when Down ask ≤ $0.35 (Up has rallied hard), exit when implied Down bid ≥ $0.55. | No | Active testing |

Each strategy is a pure function: `decide(snapshot, holds_market, position) -> TradeIntent | None`. No I/O, no globals. The same code runs in paper, backtest, and (eventually) live.

---

## Empirical Findings

Both `bot1` and `bot2_signal` have been paper-traded against live Polymarket data and exhibit negative expected value at their current parameterizations.

**Bot 1** demonstrates a structural rather than statistical failure: purchasing assets at prices the order book has already calibrated to near-certainty yields approximately zero pre-fee EV. Two paper sessions of 13 trades each produced realized hit rates above 90% but cumulative P&L of −$0.92 and −$0.70 respectively. The win/loss-magnitude asymmetry (gains of $0.01–$0.15, losses of $0.85–$0.99) is sufficient on its own to drive the strategy negative; the strategy is retained as a baseline for order-book-only momentum.

**Bot 2 (`bot2_signal`)** tested the hypothesis that the Polymarket book lags Coinbase BTC/USD movements within five-minute windows. Across six trades the realized hit rate was 33% (2W / 4L), with cumulative P&L of −$2.17. Three contributing factors were identified: an overconfident volatility prior (`sigma_per_sec_bps = 1.5`), temporal and instrumental misalignment between the Coinbase reference price and the Chainlink resolution oracle, and an asymmetric risk profile on tail-priced entries that requires hit rates well above 50% to break even. The hypothesis is not falsified at six trades but cannot be considered supported at the current parameter values.

Full analysis: [`docs/bot-postmortems.md`](docs/bot-postmortems.md).

---

## Quick Start

### 1. Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### 2. Verify there's a market to trade

```bash
python scripts/check_markets.py
```

Lists upcoming `btc-up-or-down-5m` events. If empty, the series may be paused.

### 3. Paper-trade a bot

```bash
python scripts/run_paper.py --bot bot1
python scripts/run_paper.py --bot bot2_filter
python scripts/run_paper.py --bot bot2_signal
python scripts/run_paper.py --bot bot3_dipbuyer
python scripts/run_paper.py --bot bot4_rallyfader
```

Each bot writes its recording to `recordings/<bot>/YYYY-MM-DD.jsonl`. Bots can run in parallel tabs without overwriting each other.

### 4. Replay a session

```bash
python scripts/run_backtest.py recordings/bot2_signal/2026-05-14.jsonl --bot bot2_signal
```

A recording captured by `bot2_*` or `bot3_*` includes BTC reference prices and can be replayed by any bot. A `bot1` recording has no BTC data, so `bot2_*` will skip every trade when replaying it.

### 5. Tests

```bash
pytest
```

---

## Configuration

`config.yaml` exposes per-bot parameters. Example:

```yaml
bot2_signal:
  time_window_s: [5, 20]
  trade_size_usdc: 1.00
  min_edge: 0.02
  sigma_per_sec_bps: 1.5
  price_band: [0.05, 0.99]

bot3_dipbuyer:
  entry_price: 0.35
  exit_price: 0.55
  trade_size_usdc: 5.00
```

Strategy parameters are validated by `pydantic` at load time — bad bands or non-positive sizes fail fast.

---

## Adding a New Strategy

1. Create `src/polybot/strategy/botN_yourname.py` with a class exposing `decide(snapshot, holds_market, position=None)`.
2. Add a config block to `config.py` and `config.yaml`.
3. Register it in `src/polybot/strategy/__init__.py` (`make_strategy` + `BOT_NAMES`).
4. Write tests under `tests/test_botN_yourname.py`. Mock `MarketSnapshot`s directly — no I/O needed.
5. Run `pytest`, then `python scripts/run_paper.py --bot botN_yourname`.

---

## Design Choices Worth Calling Out

- **Decimal everywhere.** Money math through `Decimal`, not `float`. The paper executor tracks `total_cost` separately from `total_shares` to avoid round-trip precision drift (e.g., `1/0.90` then `1/(1/0.90)` ≠ `0.90`).
- **Concurrent market tracking.** Discovery polls every 15s and spawns a fresh task per market within a 10-minute horizon. This avoids the "miss the next market while waiting for the current one to resolve" failure mode.
- **Deferred BTC open-price fetch.** Coinbase candles only exist after the minute closes; the bot waits until `event_start + 70s` to fetch the open price for a tracked market, instead of failing with 400s for future timestamps.
- **Synthetic bids for sells.** Polymarket binaries satisfy `Up + Down ≈ $1`, so the paper executor sells the Up side by walking the Down asks: `bid_price ≈ 1 − opp_ask_price`. Good enough for EV estimates; will need real bid data for live execution.
- **One Source of Truth for fills.** The executor writes `Fill`s; the portfolio applies them; the recorder captures them. No strategy ever mutates portfolio state directly.

---

## Roadmap

- **v2:** Live executor wired to Polymarket CLOB with wallet signing
- **v3:** Multi-strategy router (run several bots concurrently with a shared risk budget)
- **v3+:** Additional strategies — market making, taker-side rebate harvesting, cross-market correlation plays

---

## License

MIT.
