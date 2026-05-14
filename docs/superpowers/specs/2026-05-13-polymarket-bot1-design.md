# Polymarket Trading Bot — Bot 1 Design

**Date:** 2026-05-13
**Status:** Design approved, pending implementation plan
**Scope:** v1 — backtesting + paper trading for a single strategy (Bot 1). Live execution deferred to v2.

## Overview

Build a Python trading bot that targets Polymarket's recurring 5-minute Bitcoin "Up or Down" markets. The bot buys heavily-favored contracts ($0.85–$0.99) in the final seconds before resolution, capturing the small spread to $1.00 settlement.

v1 delivers a **backtester** and a **paper trader** that share strategy code, so what we validate offline matches what runs against live market data. Real execution against the Polymarket CLOB is explicitly out of scope for v1 and will be added in v2 once paper results are convincing.

## Goals

- Run Bot 1 against live Polymarket data with simulated fills and track P&L.
- Replay recorded sessions deterministically for backtesting.
- Keep strategy code mode-agnostic: the same `Strategy` runs in backtest, paper, and (eventually) live.
- Be safe: kill switches enforce daily caps even in paper mode, so the same code paths are exercised before any real money flows.

## Non-goals (v1)

- Real order placement on the CLOB (deferred to v2).
- Wallet, USDC, or API-key setup (deferred to v2).
- Additional strategies beyond Bot 1.
- Web dashboard or hosted deployment.
- Fee modeling, partial-fill handling, latency simulation.

## Strategy: Bot 1

**Market:** Polymarket's recurring 5-minute Bitcoin "Up or Down" binary market. Each instance has two outcome tokens (Up, Down) and resolves on whether BTC's price at the end of the 5-minute window is higher or lower than at the start.

**Decision rule (per market snapshot):**

```
IF time_to_resolve_s ∈ [1, 20]
   AND no open position in this market
   AND exactly one of {up_best_ask, down_best_ask} ∈ [$0.85, $0.99]:
       BUY $1 worth of that side at its best ask
ELSE:
   do nothing
```

**Properties:**
- Because Up + Down ≈ $1.00, at most one side is in the band at any moment. If both qualify (wide spread / stale book), the bot skips — ambiguous state is treated as a no-trade signal.
- One trade per market. Hold to resolution. No early exit, no averaging in.
- Strategy is stateless across markets — once a market resolves, the next market starts clean.

**Configurable parameters** (in `config.yaml`, not hardcoded):
- `price_band = [0.85, 0.99]`
- `time_window_s = [1, 20]`
- `trade_size_usdc = 1.00`
- `max_daily_trades`
- `max_daily_loss_usdc`

## Architecture

Five components wired by a `runner` for each mode.

```
┌──────────────┐    snapshot     ┌────────────┐  intent  ┌────────────┐
│  DataFeed    ├────────────────▶│  Strategy  ├─────────▶│  Executor  │
│              │  (market state) │  (Bot 1)   │ (trade)  │            │
└──────────────┘                 └────────────┘          └──────┬─────┘
       │                                                        │ fill
       │              ┌─────────────────────────────────────────┘
       ▼              ▼
┌──────────────┐  ┌────────────┐
│   Recorder   │  │ Portfolio  │   P&L, positions, resolution settlement
└──────────────┘  └────────────┘
```

### DataFeed

Interface:
```python
class DataFeed(Protocol):
    async def snapshots(self) -> AsyncIterator[MarketSnapshot]: ...
```

Yields `MarketSnapshot` objects describing the current state of an active market.

- **`LiveFeed`** — uses Polymarket Gamma API to discover the active 5-min BTC market, subscribes to the CLOB WebSocket for both outcome tokens, and emits a snapshot whenever the top of book changes (or once per second as a heartbeat so the time-window check still fires when the book is quiet).
- **`HistoricalFeed`** — reads a recorded JSONL file and yields the same `MarketSnapshot` objects in their original order. Used for backtesting.

### Strategy

Pure function. Inputs: a `MarketSnapshot` and a small view of current state (does the bot already hold this market?). Output: 0 or 1 `TradeIntent`. No I/O.

This is the same code in backtest, paper, and live — that's the central invariant of the architecture.

### Executor

Interface:
```python
class Executor(Protocol):
    async def submit(self, intent: TradeIntent) -> Fill | None: ...
```

- **`PaperExecutor`** — simulates a fill against the in-memory book.
  - Walks the ask book level-by-level until $1 of notional is filled.
  - At $1 trade size, virtually always fills at the top of book (top-of-book size dominates).
  - Returns `Fill { market_id, side, shares, avg_price, timestamp, intent_id }`.
  - No latency simulation: assumes the price observed in the latest snapshot is the price filled at.
- **`LiveExecutor`** — placeholder interface only in v1; real implementation comes in v2.

### Portfolio

- Tracks open positions per market.
- Applies fills to positions on submit.
- On resolution: queries Gamma for the market outcome, marks the winning side's shares to $1.00, the losing side to $0, and finalizes P&L for the trade.
- Maintains running totals: daily trade count, daily P&L, total P&L.
- Enforces kill switches: if `max_daily_trades` or `max_daily_loss_usdc` is breached, the runner stops accepting new intents for the day.

### Recorder

Appends every `MarketSnapshot`, `TradeIntent`, `Fill`, and resolution event as JSON Lines to `recordings/YYYY-MM-DD.jsonl`. Each paper-trade session produces a file that can be replayed via `HistoricalFeed` for backtesting.

## Polymarket API access (no auth required for v1)

- **Gamma API** (`gamma-api.polymarket.com`) — market discovery and resolution status. Polled ~once per minute to discover the next active 5-min BTC market by slug pattern.
- **CLOB API** (`clob.polymarket.com`):
  - **REST** `GET /book?token_id=...` — initial book snapshot and fallback.
  - **WebSocket** `wss://ws-subscriptions-clob.polymarket.com/ws/market` — live book updates per token ID, subscribed for both outcome tokens of the active market.

**Known risk:** the exact slug pattern and Gamma schema for these recurring markets is the most likely thing to need real-world adjustment on first run. The discovery code is isolated to `LiveFeed.discover_active_market` so the impact is contained.

## Data types

```python
@dataclass
class MarketSnapshot:
    market_id: str
    timestamp: datetime
    time_to_resolve_s: float
    up_token_id: str
    down_token_id: str
    up_best_ask: Decimal | None
    up_best_ask_size: Decimal | None
    down_best_ask: Decimal | None
    down_best_ask_size: Decimal | None
    # full book levels available for executor's walk-the-book fill model

@dataclass
class TradeIntent:
    intent_id: str
    market_id: str
    side: Literal["up", "down"]
    notional_usdc: Decimal  # always 1.00 for Bot 1

@dataclass
class Fill:
    intent_id: str
    market_id: str
    side: Literal["up", "down"]
    shares: Decimal
    avg_price: Decimal
    timestamp: datetime

@dataclass
class Position:
    market_id: str
    side: Literal["up", "down"]
    shares: Decimal
    cost_usdc: Decimal
    opened_at: datetime
    resolved: bool = False
    pnl_usdc: Decimal | None = None
```

## Project layout

```
polymarket-bot/
├── pyproject.toml          # deps: httpx, websockets, pydantic, pytest, ruff
├── config.yaml             # strategy params + kill switches
├── src/polybot/
│   ├── types.py
│   ├── feed/
│   │   ├── base.py
│   │   ├── live.py
│   │   └── historical.py
│   ├── strategy/
│   │   └── bot1.py
│   ├── executor/
│   │   ├── base.py
│   │   └── paper.py
│   ├── portfolio.py
│   ├── recorder.py
│   └── runner.py
├── scripts/
│   ├── run_paper.py
│   └── run_backtest.py
├── recordings/             # JSONL files from paper runs
└── tests/
    ├── test_strategy.py
    ├── test_paper_executor.py
    ├── test_portfolio.py
    └── test_historical_feed.py
```

## Run modes

| Mode      | DataFeed         | Executor       | Invoked by                       |
|-----------|------------------|----------------|----------------------------------|
| Backtest  | `HistoricalFeed` | `PaperExecutor`| `scripts/run_backtest.py <file>` |
| Paper     | `LiveFeed`       | `PaperExecutor`| `scripts/run_paper.py`           |
| Live (v2) | `LiveFeed`       | `LiveExecutor` | (deferred)                       |

Mode is purely a wiring choice in `runner.py`. The Strategy, Portfolio, and Recorder are identical across all modes.

## Testing approach

- **Unit tests for Strategy** — tabletop cases covering: in-band + in-window → trade; in-band but outside window → no trade; in window but outside band → no trade; already holding position → no trade; both sides somehow in band → no trade.
- **Unit tests for PaperExecutor** — fill at top of book; book-walk when notional exceeds top level (synthetic case).
- **Unit tests for Portfolio** — fill application, resolution settlement (win and loss), kill-switch triggering.
- **Unit tests for HistoricalFeed** — replays a fixed JSONL into the expected sequence of snapshots.
- **Integration smoke test** — wire `HistoricalFeed + Strategy + PaperExecutor + Portfolio` against a small recorded fixture; assert end-of-run P&L matches expectation.

## Observability

- Structured logs to stdout (one line per snapshot decision, intent, fill, resolution).
- JSONL recording on disk for the full session.
- CLI prints a running summary every N seconds: trades today, current open positions, day P&L, total P&L.

## Path to v2 (live trading)

When paper results are convincing:
1. Set up Polygon wallet, fund with USDC, generate CLOB API credentials, approve allowances.
2. Implement `LiveExecutor` against the CLOB REST API.
3. Add latency observation (record submit-to-fill duration) and a minimum-acceptable-price guard.
4. Run live with the smallest possible size (the same $1) before scaling.

v2 is a separate spec and plan.
