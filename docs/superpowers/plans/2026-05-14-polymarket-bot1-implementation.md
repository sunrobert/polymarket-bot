# Polymarket Bot 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build Bot 1 — a Polymarket trading bot that backtests + paper-trades the 5-minute BTC "Up or Down" market by buying favored contracts ($0.85–$0.99) in the final 1–20s before resolution, for a fixed $1 per trade.

**Architecture:** Five components wired by a `runner` per mode — `DataFeed` (Live/Historical), pure `Strategy`, `Executor` (Paper only in v1), pure `Portfolio`, and `Recorder`. Strategy/Portfolio/Recorder are identical across modes; mode is a wiring choice. **v1 ships paper + backtest only; no live order placement code is included.** Real CLOB trading is deferred to v2.

**Tech Stack:** Python 3.11+, `httpx` (Gamma REST + CLOB REST), `websockets` (CLOB WS), `pydantic` (config + types), `pytest` (tests), `ruff` (lint), `pyyaml` (config), `decimal.Decimal` for all money math.

---

## File Structure

```
polymarket-bot/
├── pyproject.toml
├── config.yaml
├── src/polybot/
│   ├── __init__.py
│   ├── types.py              # MarketSnapshot, ResolutionEvent, TradeIntent, Fill, Position, BookLevel, FeedEvent
│   ├── config.py             # load_config() -> Config (pydantic)
│   ├── feed/
│   │   ├── __init__.py
│   │   ├── base.py           # DataFeed Protocol
│   │   ├── historical.py     # HistoricalFeed (reads JSONL)
│   │   └── live.py           # LiveFeed (Gamma discovery + CLOB WS)
│   ├── strategy/
│   │   ├── __init__.py
│   │   └── bot1.py           # Bot1Strategy.decide(snapshot, holds) -> TradeIntent | None
│   ├── executor/
│   │   ├── __init__.py
│   │   ├── base.py           # Executor Protocol
│   │   └── paper.py          # PaperExecutor: walks book against snapshot
│   ├── portfolio.py          # Portfolio: positions, fills, resolutions, kill switches
│   ├── recorder.py           # Recorder: appends JSONL to recordings/
│   └── runner.py             # async run_loop(feed, strategy, executor, portfolio, recorder, config)
├── scripts/
│   ├── run_paper.py
│   └── run_backtest.py
├── recordings/               # gitignored, created at runtime
└── tests/
    ├── __init__.py
    ├── fixtures/
    │   └── tiny_session.jsonl
    ├── test_types.py
    ├── test_config.py
    ├── test_recorder.py
    ├── test_portfolio.py
    ├── test_paper_executor.py
    ├── test_strategy.py
    ├── test_historical_feed.py
    └── test_runner_integration.py
```

Each file has one responsibility; tests sit beside the unit they cover. No `live.py` test in v1 because it's all I/O glue against external services — we'll smoke-test it manually with `run_paper.py`.

---

## Task 1: Project Scaffold

**Files:**
- Create: `pyproject.toml`
- Create: `config.yaml`
- Create: `.gitignore`
- Create: `src/polybot/__init__.py`
- Create: `tests/__init__.py`
- Create: `README.md`

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[project]
name = "polybot"
version = "0.1.0"
description = "Polymarket Bot 1 — 5-minute BTC up/down paper trader"
requires-python = ">=3.11"
dependencies = [
  "httpx>=0.27",
  "websockets>=12.0",
  "pydantic>=2.6",
  "pyyaml>=6.0",
]

[project.optional-dependencies]
dev = [
  "pytest>=8.0",
  "pytest-asyncio>=0.23",
  "ruff>=0.4",
]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.ruff]
line-length = 100
target-version = "py311"
```

- [ ] **Step 2: Create `config.yaml`**

```yaml
strategy:
  price_band: [0.85, 0.99]
  time_window_s: [1, 20]
  trade_size_usdc: 1.00

risk:
  max_daily_trades: 50
  max_daily_loss_usdc: 10.00

recorder:
  dir: recordings

feed:
  # Pattern used by LiveFeed.discover_active_market to find the current 5-min BTC market.
  # Likely to need real-world adjustment on first run.
  gamma_url: https://gamma-api.polymarket.com
  clob_ws_url: wss://ws-subscriptions-clob.polymarket.com/ws/market
  clob_rest_url: https://clob.polymarket.com
  market_slug_substring: bitcoin-up-or-down
  heartbeat_interval_s: 1.0
  resolution_poll_interval_s: 5.0
```

- [ ] **Step 3: Create `.gitignore`**

```gitignore
__pycache__/
*.pyc
.pytest_cache/
.ruff_cache/
*.egg-info/
.venv/
recordings/
.DS_Store
```

- [ ] **Step 4: Create empty package init files**

`src/polybot/__init__.py`:
```python
"""Polymarket Bot 1."""
```

`tests/__init__.py`:
```python
```

- [ ] **Step 5: Create `README.md`**

```markdown
# polybot

Polymarket Bot 1 — paper trader and backtester for the recurring 5-minute Bitcoin
"Up or Down" market. Buys heavily-favored contracts ($0.85–$0.99) in the final
1–20 seconds before resolution, $1 per trade.

**v1 is paper trading only.** Live execution against the CLOB is deferred to v2.

## Setup

    python -m venv .venv
    source .venv/bin/activate
    pip install -e ".[dev]"

## Run

    python scripts/run_paper.py            # paper trade against live data
    python scripts/run_backtest.py FILE    # replay a recorded session

## Test

    pytest
```

- [ ] **Step 6: Verify install works**

Run:
```bash
python -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"
```
Expected: Successful install of httpx, websockets, pydantic, pyyaml, pytest, pytest-asyncio, ruff.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml config.yaml .gitignore src/polybot/__init__.py tests/__init__.py README.md
git commit -m "feat: project scaffold for polybot"
```

---

## Task 2: Core Types

**Files:**
- Create: `src/polybot/types.py`
- Test: `tests/test_types.py`

- [ ] **Step 1: Write the failing test**

`tests/test_types.py`:
```python
from datetime import datetime, timezone
from decimal import Decimal

from polybot.types import (
    BookLevel,
    Fill,
    MarketSnapshot,
    Position,
    ResolutionEvent,
    TradeIntent,
)


def _ts():
    return datetime(2026, 5, 14, 12, 0, 0, tzinfo=timezone.utc)


def test_market_snapshot_holds_book_state():
    snap = MarketSnapshot(
        market_id="m1",
        timestamp=_ts(),
        time_to_resolve_s=10.0,
        up_token_id="u",
        down_token_id="d",
        up_best_ask=Decimal("0.90"),
        up_best_ask_size=Decimal("100"),
        down_best_ask=Decimal("0.12"),
        down_best_ask_size=Decimal("100"),
        up_asks=[BookLevel(price=Decimal("0.90"), size=Decimal("100"))],
        down_asks=[BookLevel(price=Decimal("0.12"), size=Decimal("100"))],
    )
    assert snap.up_best_ask == Decimal("0.90")
    assert snap.up_asks[0].size == Decimal("100")


def test_resolution_event_winning_side():
    ev = ResolutionEvent(market_id="m1", timestamp=_ts(), winning_side="up")
    assert ev.winning_side == "up"


def test_trade_intent_carries_size():
    intent = TradeIntent(
        intent_id="i1", market_id="m1", side="up", notional_usdc=Decimal("1.00")
    )
    assert intent.notional_usdc == Decimal("1.00")


def test_fill_round_trip():
    fill = Fill(
        intent_id="i1",
        market_id="m1",
        side="up",
        shares=Decimal("1.111111"),
        avg_price=Decimal("0.90"),
        timestamp=_ts(),
    )
    assert fill.shares * fill.avg_price <= Decimal("1.00")


def test_position_defaults_unresolved():
    pos = Position(
        market_id="m1",
        side="up",
        shares=Decimal("1.1"),
        cost_usdc=Decimal("1.00"),
        opened_at=_ts(),
    )
    assert pos.resolved is False
    assert pos.pnl_usdc is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_types.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'polybot.types'`

- [ ] **Step 3: Implement types**

`src/polybot/types.py`:
```python
"""Core data types. Decimal everywhere for money. No I/O lives here."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Literal, Union

Side = Literal["up", "down"]


@dataclass(frozen=True)
class BookLevel:
    price: Decimal
    size: Decimal


@dataclass(frozen=True)
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
    up_asks: list[BookLevel] = field(default_factory=list)
    down_asks: list[BookLevel] = field(default_factory=list)


@dataclass(frozen=True)
class ResolutionEvent:
    market_id: str
    timestamp: datetime
    winning_side: Side


FeedEvent = Union[MarketSnapshot, ResolutionEvent]


@dataclass(frozen=True)
class TradeIntent:
    intent_id: str
    market_id: str
    side: Side
    notional_usdc: Decimal


@dataclass(frozen=True)
class Fill:
    intent_id: str
    market_id: str
    side: Side
    shares: Decimal
    avg_price: Decimal
    timestamp: datetime


@dataclass
class Position:
    market_id: str
    side: Side
    shares: Decimal
    cost_usdc: Decimal
    opened_at: datetime
    resolved: bool = False
    pnl_usdc: Decimal | None = None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_types.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add src/polybot/types.py tests/test_types.py
git commit -m "feat: core data types for polybot"
```

---

## Task 3: Config Loader

**Files:**
- Create: `src/polybot/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

`tests/test_config.py`:
```python
from decimal import Decimal
from pathlib import Path

import pytest

from polybot.config import Config, load_config


YAML = """
strategy:
  price_band: [0.85, 0.99]
  time_window_s: [1, 20]
  trade_size_usdc: 1.00
risk:
  max_daily_trades: 50
  max_daily_loss_usdc: 10.00
recorder:
  dir: recordings
feed:
  gamma_url: https://gamma-api.polymarket.com
  clob_ws_url: wss://ws-subscriptions-clob.polymarket.com/ws/market
  clob_rest_url: https://clob.polymarket.com
  market_slug_substring: bitcoin-up-or-down
  heartbeat_interval_s: 1.0
  resolution_poll_interval_s: 5.0
"""


def test_load_config_parses_decimal(tmp_path: Path):
    p = tmp_path / "c.yaml"
    p.write_text(YAML)
    cfg = load_config(p)
    assert isinstance(cfg, Config)
    assert cfg.strategy.price_band == (Decimal("0.85"), Decimal("0.99"))
    assert cfg.strategy.time_window_s == (1.0, 20.0)
    assert cfg.strategy.trade_size_usdc == Decimal("1.00")
    assert cfg.risk.max_daily_trades == 50
    assert cfg.risk.max_daily_loss_usdc == Decimal("10.00")
    assert cfg.recorder.dir == "recordings"
    assert cfg.feed.market_slug_substring == "bitcoin-up-or-down"


def test_load_config_rejects_bad_band(tmp_path: Path):
    p = tmp_path / "c.yaml"
    p.write_text(YAML.replace("[0.85, 0.99]", "[0.99, 0.85]"))
    with pytest.raises(ValueError):
        load_config(p)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement config**

`src/polybot/config.py`:
```python
"""Config loader. YAML on disk → pydantic models in memory."""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator


class StrategyConfig(BaseModel):
    price_band: tuple[Decimal, Decimal]
    time_window_s: tuple[float, float]
    trade_size_usdc: Decimal

    @model_validator(mode="after")
    def _ordered_band(self) -> "StrategyConfig":
        lo, hi = self.price_band
        if lo >= hi:
            raise ValueError(f"price_band must be increasing, got {self.price_band}")
        w_lo, w_hi = self.time_window_s
        if w_lo >= w_hi:
            raise ValueError(f"time_window_s must be increasing, got {self.time_window_s}")
        if self.trade_size_usdc <= 0:
            raise ValueError("trade_size_usdc must be > 0")
        return self


class RiskConfig(BaseModel):
    max_daily_trades: int = Field(gt=0)
    max_daily_loss_usdc: Decimal = Field(gt=0)


class RecorderConfig(BaseModel):
    dir: str


class FeedConfig(BaseModel):
    gamma_url: str
    clob_ws_url: str
    clob_rest_url: str
    market_slug_substring: str
    heartbeat_interval_s: float = Field(gt=0)
    resolution_poll_interval_s: float = Field(gt=0)


class Config(BaseModel):
    strategy: StrategyConfig
    risk: RiskConfig
    recorder: RecorderConfig
    feed: FeedConfig


def load_config(path: Path | str) -> Config:
    raw = yaml.safe_load(Path(path).read_text())
    return Config.model_validate(raw)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_config.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add src/polybot/config.py tests/test_config.py
git commit -m "feat: pydantic config loader"
```

---

## Task 4: Strategy (Bot 1)

**Files:**
- Create: `src/polybot/strategy/__init__.py`
- Create: `src/polybot/strategy/bot1.py`
- Test: `tests/test_strategy.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_strategy.py`:
```python
from datetime import datetime, timezone
from decimal import Decimal

from polybot.strategy.bot1 import Bot1Strategy
from polybot.types import BookLevel, MarketSnapshot


def _snap(
    *,
    ttr: float,
    up_ask: Decimal | None,
    down_ask: Decimal | None,
    market_id: str = "m1",
) -> MarketSnapshot:
    return MarketSnapshot(
        market_id=market_id,
        timestamp=datetime(2026, 5, 14, 12, 0, 0, tzinfo=timezone.utc),
        time_to_resolve_s=ttr,
        up_token_id="u",
        down_token_id="d",
        up_best_ask=up_ask,
        up_best_ask_size=Decimal("100") if up_ask else None,
        down_best_ask=down_ask,
        down_best_ask_size=Decimal("100") if down_ask else None,
        up_asks=[BookLevel(price=up_ask, size=Decimal("100"))] if up_ask else [],
        down_asks=[BookLevel(price=down_ask, size=Decimal("100"))] if down_ask else [],
    )


def _strategy() -> Bot1Strategy:
    return Bot1Strategy(
        price_band=(Decimal("0.85"), Decimal("0.99")),
        time_window_s=(1.0, 20.0),
        trade_size_usdc=Decimal("1.00"),
    )


def test_in_band_in_window_up_emits_intent():
    s = _strategy()
    snap = _snap(ttr=10, up_ask=Decimal("0.92"), down_ask=Decimal("0.10"))
    intent = s.decide(snap, holds_market=False)
    assert intent is not None
    assert intent.side == "up"
    assert intent.market_id == "m1"
    assert intent.notional_usdc == Decimal("1.00")


def test_in_band_in_window_down_emits_intent():
    s = _strategy()
    snap = _snap(ttr=5, up_ask=Decimal("0.10"), down_ask=Decimal("0.92"))
    intent = s.decide(snap, holds_market=False)
    assert intent is not None
    assert intent.side == "down"


def test_outside_window_too_early_no_trade():
    s = _strategy()
    snap = _snap(ttr=30, up_ask=Decimal("0.92"), down_ask=Decimal("0.10"))
    assert s.decide(snap, holds_market=False) is None


def test_outside_window_too_late_no_trade():
    s = _strategy()
    snap = _snap(ttr=0.5, up_ask=Decimal("0.92"), down_ask=Decimal("0.10"))
    assert s.decide(snap, holds_market=False) is None


def test_in_window_below_band_no_trade():
    s = _strategy()
    snap = _snap(ttr=10, up_ask=Decimal("0.80"), down_ask=Decimal("0.22"))
    assert s.decide(snap, holds_market=False) is None


def test_in_window_above_band_no_trade():
    s = _strategy()
    snap = _snap(ttr=10, up_ask=Decimal("0.999"), down_ask=Decimal("0.005"))
    assert s.decide(snap, holds_market=False) is None


def test_already_holding_no_trade():
    s = _strategy()
    snap = _snap(ttr=10, up_ask=Decimal("0.92"), down_ask=Decimal("0.10"))
    assert s.decide(snap, holds_market=True) is None


def test_both_sides_in_band_ambiguous_no_trade():
    s = _strategy()
    snap = _snap(ttr=10, up_ask=Decimal("0.90"), down_ask=Decimal("0.88"))
    assert s.decide(snap, holds_market=False) is None


def test_missing_ask_treated_as_not_in_band():
    s = _strategy()
    snap = _snap(ttr=10, up_ask=None, down_ask=Decimal("0.92"))
    intent = s.decide(snap, holds_market=False)
    assert intent is not None
    assert intent.side == "down"


def test_intent_id_is_stable_per_market_decision():
    s = _strategy()
    snap = _snap(ttr=10, up_ask=Decimal("0.92"), down_ask=Decimal("0.10"))
    i1 = s.decide(snap, holds_market=False)
    i2 = s.decide(snap, holds_market=False)
    assert i1 is not None and i2 is not None
    assert i1.intent_id != i2.intent_id  # each call produces a fresh id
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_strategy.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Create strategy package init**

`src/polybot/strategy/__init__.py`:
```python
```

- [ ] **Step 4: Implement Bot1Strategy**

`src/polybot/strategy/bot1.py`:
```python
"""Bot 1: buy heavily-favored 5-min BTC up/down in the final 1-20s before resolution.

Pure function. No I/O. Same code runs in backtest, paper, and (eventually) live.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

from polybot.types import MarketSnapshot, Side, TradeIntent


class Bot1Strategy:
    def __init__(
        self,
        price_band: tuple[Decimal, Decimal],
        time_window_s: tuple[float, float],
        trade_size_usdc: Decimal,
    ) -> None:
        self.price_band = price_band
        self.time_window_s = time_window_s
        self.trade_size_usdc = trade_size_usdc

    def decide(
        self, snapshot: MarketSnapshot, holds_market: bool
    ) -> TradeIntent | None:
        if holds_market:
            return None

        lo_t, hi_t = self.time_window_s
        if not (lo_t <= snapshot.time_to_resolve_s <= hi_t):
            return None

        lo_p, hi_p = self.price_band
        up_in = (
            snapshot.up_best_ask is not None and lo_p <= snapshot.up_best_ask <= hi_p
        )
        down_in = (
            snapshot.down_best_ask is not None
            and lo_p <= snapshot.down_best_ask <= hi_p
        )

        # Ambiguous: both sides in band means the book is wide/stale. Skip.
        if up_in == down_in:
            return None

        side: Side = "up" if up_in else "down"
        return TradeIntent(
            intent_id=str(uuid.uuid4()),
            market_id=snapshot.market_id,
            side=side,
            notional_usdc=self.trade_size_usdc,
        )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_strategy.py -v`
Expected: 10 passed

- [ ] **Step 6: Commit**

```bash
git add src/polybot/strategy/__init__.py src/polybot/strategy/bot1.py tests/test_strategy.py
git commit -m "feat: Bot1 strategy with TDD"
```

---

## Task 5: Paper Executor

**Files:**
- Create: `src/polybot/executor/__init__.py`
- Create: `src/polybot/executor/base.py`
- Create: `src/polybot/executor/paper.py`
- Test: `tests/test_paper_executor.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_paper_executor.py`:
```python
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from polybot.executor.paper import PaperExecutor
from polybot.types import BookLevel, MarketSnapshot, TradeIntent


def _ts():
    return datetime(2026, 5, 14, 12, 0, 0, tzinfo=timezone.utc)


def _snap_with_up_asks(levels: list[tuple[str, str]]) -> MarketSnapshot:
    asks = [BookLevel(price=Decimal(p), size=Decimal(s)) for p, s in levels]
    return MarketSnapshot(
        market_id="m1",
        timestamp=_ts(),
        time_to_resolve_s=5,
        up_token_id="u",
        down_token_id="d",
        up_best_ask=asks[0].price if asks else None,
        up_best_ask_size=asks[0].size if asks else None,
        down_best_ask=Decimal("0.10"),
        down_best_ask_size=Decimal("1000"),
        up_asks=asks,
        down_asks=[BookLevel(price=Decimal("0.10"), size=Decimal("1000"))],
    )


async def test_fills_at_top_when_size_dominates():
    ex = PaperExecutor()
    snap = _snap_with_up_asks([("0.90", "1000")])
    ex.on_snapshot(snap)
    intent = TradeIntent(
        intent_id="i1", market_id="m1", side="up", notional_usdc=Decimal("1.00")
    )
    fill = await ex.submit(intent)
    assert fill is not None
    assert fill.avg_price == Decimal("0.90")
    # $1 / $0.90 ≈ 1.1111 shares
    assert fill.shares == Decimal("1") / Decimal("0.90")


async def test_walks_book_when_top_level_too_thin():
    ex = PaperExecutor()
    # Top level: 0.5 shares @ $0.90 → $0.45 of notional.
    # Next level:  1.0 shares @ $0.95 → fills remaining $0.55 = 0.5789... shares.
    snap = _snap_with_up_asks([("0.90", "0.5"), ("0.95", "1.0")])
    ex.on_snapshot(snap)
    intent = TradeIntent(
        intent_id="i2", market_id="m1", side="up", notional_usdc=Decimal("1.00")
    )
    fill = await ex.submit(intent)
    assert fill is not None
    # avg_price = $1 / shares; shares = 0.5 + 0.55/0.95
    expected_shares = Decimal("0.5") + (Decimal("0.55") / Decimal("0.95"))
    assert fill.shares == expected_shares
    assert fill.avg_price == Decimal("1.00") / expected_shares


async def test_no_snapshot_returns_none():
    ex = PaperExecutor()
    intent = TradeIntent(
        intent_id="i3", market_id="m1", side="up", notional_usdc=Decimal("1.00")
    )
    assert await ex.submit(intent) is None


async def test_empty_book_returns_none():
    ex = PaperExecutor()
    ex.on_snapshot(_snap_with_up_asks([]))
    intent = TradeIntent(
        intent_id="i4", market_id="m1", side="up", notional_usdc=Decimal("1.00")
    )
    assert await ex.submit(intent) is None


async def test_book_too_thin_to_fill_returns_none():
    ex = PaperExecutor()
    # Only $0.40 of liquidity total; $1 intent can't fill.
    snap = _snap_with_up_asks([("0.80", "0.5")])
    ex.on_snapshot(snap)
    intent = TradeIntent(
        intent_id="i5", market_id="m1", side="up", notional_usdc=Decimal("1.00")
    )
    assert await ex.submit(intent) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_paper_executor.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Create executor package init**

`src/polybot/executor/__init__.py`:
```python
```

- [ ] **Step 4: Implement Executor protocol**

`src/polybot/executor/base.py`:
```python
"""Executor interface. Paper in v1; live in v2."""
from __future__ import annotations

from typing import Protocol

from polybot.types import Fill, TradeIntent


class Executor(Protocol):
    async def submit(self, intent: TradeIntent) -> Fill | None: ...
```

- [ ] **Step 5: Implement PaperExecutor**

`src/polybot/executor/paper.py`:
```python
"""Paper executor: walks the latest in-memory book to simulate a fill.

Assumes the price observed in the most recent snapshot is the price filled at —
no latency simulation. Returns None if no snapshot has been seen yet or if the
book lacks the liquidity to fill the requested notional.
"""
from __future__ import annotations

from decimal import Decimal

from polybot.types import BookLevel, Fill, MarketSnapshot, Side, TradeIntent


class PaperExecutor:
    def __init__(self) -> None:
        self._latest: dict[str, MarketSnapshot] = {}

    def on_snapshot(self, snapshot: MarketSnapshot) -> None:
        self._latest[snapshot.market_id] = snapshot

    async def submit(self, intent: TradeIntent) -> Fill | None:
        snap = self._latest.get(intent.market_id)
        if snap is None:
            return None
        asks = self._asks_for(snap, intent.side)
        if not asks:
            return None

        remaining = intent.notional_usdc
        total_shares = Decimal("0")

        for level in asks:
            if remaining <= 0:
                break
            level_notional = level.price * level.size
            if level_notional >= remaining:
                total_shares += remaining / level.price
                remaining = Decimal("0")
                break
            total_shares += level.size
            remaining -= level_notional

        if remaining > 0:
            # Not enough liquidity to fill the intent at any price.
            return None

        avg_price = intent.notional_usdc / total_shares
        return Fill(
            intent_id=intent.intent_id,
            market_id=intent.market_id,
            side=intent.side,
            shares=total_shares,
            avg_price=avg_price,
            timestamp=snap.timestamp,
        )

    @staticmethod
    def _asks_for(snap: MarketSnapshot, side: Side) -> list[BookLevel]:
        return snap.up_asks if side == "up" else snap.down_asks
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_paper_executor.py -v`
Expected: 5 passed

- [ ] **Step 7: Commit**

```bash
git add src/polybot/executor/ tests/test_paper_executor.py
git commit -m "feat: paper executor with book walk"
```

---

## Task 6: Portfolio

**Files:**
- Create: `src/polybot/portfolio.py`
- Test: `tests/test_portfolio.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_portfolio.py`:
```python
from datetime import datetime, timezone
from decimal import Decimal

from polybot.portfolio import Portfolio
from polybot.types import Fill, ResolutionEvent


def _ts():
    return datetime(2026, 5, 14, 12, 0, 0, tzinfo=timezone.utc)


def _fill(market_id: str = "m1", side: str = "up") -> Fill:
    # $1 of notional at $0.90 → 1.1111... shares
    shares = Decimal("1.00") / Decimal("0.90")
    return Fill(
        intent_id=f"i-{market_id}",
        market_id=market_id,
        side=side,  # type: ignore[arg-type]
        shares=shares,
        avg_price=Decimal("0.90"),
        timestamp=_ts(),
    )


def test_holds_market_after_fill():
    p = Portfolio(max_daily_trades=10, max_daily_loss_usdc=Decimal("10"))
    assert not p.holds_market("m1")
    p.apply_fill(_fill())
    assert p.holds_market("m1")


def test_winning_resolution_pays_one_dollar_per_share():
    p = Portfolio(max_daily_trades=10, max_daily_loss_usdc=Decimal("10"))
    p.apply_fill(_fill(side="up"))
    p.apply_resolution(ResolutionEvent(market_id="m1", timestamp=_ts(), winning_side="up"))
    # shares ≈ 1.1111, cost $1 → P&L ≈ $0.1111
    expected = (Decimal("1.00") / Decimal("0.90")) - Decimal("1.00")
    assert p.day_pnl == expected
    assert p.total_pnl == expected


def test_losing_resolution_loses_cost():
    p = Portfolio(max_daily_trades=10, max_daily_loss_usdc=Decimal("10"))
    p.apply_fill(_fill(side="up"))
    p.apply_resolution(
        ResolutionEvent(market_id="m1", timestamp=_ts(), winning_side="down")
    )
    assert p.day_pnl == Decimal("-1.00")


def test_kill_switch_max_daily_trades():
    p = Portfolio(max_daily_trades=2, max_daily_loss_usdc=Decimal("10"))
    p.apply_fill(_fill(market_id="m1"))
    p.apply_fill(_fill(market_id="m2"))
    assert p.day_trades == 2
    assert p.is_halted() is True


def test_kill_switch_max_daily_loss():
    p = Portfolio(max_daily_trades=100, max_daily_loss_usdc=Decimal("1.50"))
    p.apply_fill(_fill(market_id="m1"))
    p.apply_resolution(
        ResolutionEvent(market_id="m1", timestamp=_ts(), winning_side="down")
    )
    p.apply_fill(_fill(market_id="m2"))
    p.apply_resolution(
        ResolutionEvent(market_id="m2", timestamp=_ts(), winning_side="down")
    )
    # day_pnl ≈ -$2.00, exceeds -$1.50
    assert p.is_halted() is True


def test_not_halted_initially():
    p = Portfolio(max_daily_trades=10, max_daily_loss_usdc=Decimal("10"))
    assert p.is_halted() is False


def test_resolution_for_unknown_market_is_noop():
    p = Portfolio(max_daily_trades=10, max_daily_loss_usdc=Decimal("10"))
    p.apply_resolution(
        ResolutionEvent(market_id="ghost", timestamp=_ts(), winning_side="up")
    )
    assert p.day_pnl == Decimal("0")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_portfolio.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement Portfolio**

`src/polybot/portfolio.py`:
```python
"""Portfolio: positions, fills, resolutions, kill switches. No I/O."""
from __future__ import annotations

from decimal import Decimal

from polybot.types import Fill, Position, ResolutionEvent


class Portfolio:
    def __init__(
        self, max_daily_trades: int, max_daily_loss_usdc: Decimal
    ) -> None:
        self._max_daily_trades = max_daily_trades
        self._max_daily_loss_usdc = max_daily_loss_usdc
        self._positions: dict[str, Position] = {}
        self.day_trades: int = 0
        self.day_pnl: Decimal = Decimal("0")
        self.total_pnl: Decimal = Decimal("0")

    def holds_market(self, market_id: str) -> bool:
        pos = self._positions.get(market_id)
        return pos is not None and not pos.resolved

    def apply_fill(self, fill: Fill) -> None:
        cost = fill.shares * fill.avg_price
        self._positions[fill.market_id] = Position(
            market_id=fill.market_id,
            side=fill.side,
            shares=fill.shares,
            cost_usdc=cost,
            opened_at=fill.timestamp,
        )
        self.day_trades += 1

    def apply_resolution(self, event: ResolutionEvent) -> None:
        pos = self._positions.get(event.market_id)
        if pos is None or pos.resolved:
            return
        payout = pos.shares if pos.side == event.winning_side else Decimal("0")
        pnl = payout - pos.cost_usdc
        pos.resolved = True
        pos.pnl_usdc = pnl
        self.day_pnl += pnl
        self.total_pnl += pnl

    def is_halted(self) -> bool:
        if self.day_trades >= self._max_daily_trades:
            return True
        if self.day_pnl <= -self._max_daily_loss_usdc:
            return True
        return False

    def open_positions(self) -> list[Position]:
        return [p for p in self._positions.values() if not p.resolved]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_portfolio.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add src/polybot/portfolio.py tests/test_portfolio.py
git commit -m "feat: portfolio with kill switches"
```

---

## Task 7: Recorder

**Files:**
- Create: `src/polybot/recorder.py`
- Test: `tests/test_recorder.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_recorder.py`:
```python
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from polybot.recorder import Recorder
from polybot.types import (
    BookLevel,
    Fill,
    MarketSnapshot,
    ResolutionEvent,
    TradeIntent,
)


def _ts():
    return datetime(2026, 5, 14, 12, 0, 0, tzinfo=timezone.utc)


def test_records_each_event_as_one_line(tmp_path: Path):
    rec = Recorder(dir=tmp_path, now=_ts)
    snap = MarketSnapshot(
        market_id="m1",
        timestamp=_ts(),
        time_to_resolve_s=10,
        up_token_id="u",
        down_token_id="d",
        up_best_ask=Decimal("0.90"),
        up_best_ask_size=Decimal("100"),
        down_best_ask=Decimal("0.10"),
        down_best_ask_size=Decimal("100"),
        up_asks=[BookLevel(price=Decimal("0.90"), size=Decimal("100"))],
        down_asks=[BookLevel(price=Decimal("0.10"), size=Decimal("100"))],
    )
    intent = TradeIntent(
        intent_id="i1", market_id="m1", side="up", notional_usdc=Decimal("1.00")
    )
    fill = Fill(
        intent_id="i1",
        market_id="m1",
        side="up",
        shares=Decimal("1.111"),
        avg_price=Decimal("0.90"),
        timestamp=_ts(),
    )
    res = ResolutionEvent(market_id="m1", timestamp=_ts(), winning_side="up")

    rec.record_snapshot(snap)
    rec.record_intent(intent)
    rec.record_fill(fill)
    rec.record_resolution(res)
    rec.close()

    files = list(tmp_path.glob("*.jsonl"))
    assert len(files) == 1
    lines = files[0].read_text().splitlines()
    assert len(lines) == 4
    parsed = [json.loads(l) for l in lines]
    assert parsed[0]["type"] == "snapshot"
    assert parsed[0]["up_best_ask"] == "0.90"
    assert parsed[1]["type"] == "intent"
    assert parsed[2]["type"] == "fill"
    assert parsed[3]["type"] == "resolution"
    assert parsed[3]["winning_side"] == "up"


def test_filename_uses_session_date(tmp_path: Path):
    fixed = datetime(2026, 5, 14, 12, 0, 0, tzinfo=timezone.utc)
    rec = Recorder(dir=tmp_path, now=lambda: fixed)
    rec.record_resolution(
        ResolutionEvent(market_id="m1", timestamp=fixed, winning_side="up")
    )
    rec.close()
    files = list(tmp_path.glob("*.jsonl"))
    assert files[0].name == "2026-05-14.jsonl"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_recorder.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement Recorder**

`src/polybot/recorder.py`:
```python
"""JSON Lines recorder. Every snapshot, intent, fill, and resolution gets one line.

Output files match `recordings/YYYY-MM-DD.jsonl` where the date is when the
recorder was constructed (one file per session).
"""
from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Callable, IO

from polybot.types import Fill, MarketSnapshot, ResolutionEvent, TradeIntent


def _default_now() -> datetime:
    return datetime.now(timezone.utc)


def _encode(obj):
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    if is_dataclass(obj):
        return asdict(obj)
    raise TypeError(f"Unserializable: {type(obj)}")


class Recorder:
    def __init__(
        self,
        dir: Path | str,
        now: Callable[[], datetime] = _default_now,
    ) -> None:
        self._dir = Path(dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        date_str = now().date().isoformat()
        self._path = self._dir / f"{date_str}.jsonl"
        self._fh: IO[str] = self._path.open("a", encoding="utf-8")

    @property
    def path(self) -> Path:
        return self._path

    def record_snapshot(self, snap: MarketSnapshot) -> None:
        self._write("snapshot", asdict(snap))

    def record_intent(self, intent: TradeIntent) -> None:
        self._write("intent", asdict(intent))

    def record_fill(self, fill: Fill) -> None:
        self._write("fill", asdict(fill))

    def record_resolution(self, event: ResolutionEvent) -> None:
        self._write("resolution", asdict(event))

    def _write(self, event_type: str, payload: dict) -> None:
        payload = {"type": event_type, **payload}
        self._fh.write(json.dumps(payload, default=_encode) + "\n")
        self._fh.flush()

    def close(self) -> None:
        if not self._fh.closed:
            self._fh.close()

    def __enter__(self) -> "Recorder":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_recorder.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add src/polybot/recorder.py tests/test_recorder.py
git commit -m "feat: JSONL recorder"
```

---

## Task 8: Feed Base + Historical Feed

**Files:**
- Create: `src/polybot/feed/__init__.py`
- Create: `src/polybot/feed/base.py`
- Create: `src/polybot/feed/historical.py`
- Create: `tests/fixtures/tiny_session.jsonl`
- Test: `tests/test_historical_feed.py`

- [ ] **Step 1: Write the failing tests**

`tests/fixtures/tiny_session.jsonl`:
```jsonl
{"type":"snapshot","market_id":"m1","timestamp":"2026-05-14T12:00:00+00:00","time_to_resolve_s":15,"up_token_id":"u","down_token_id":"d","up_best_ask":"0.92","up_best_ask_size":"100","down_best_ask":"0.10","down_best_ask_size":"100","up_asks":[{"price":"0.92","size":"100"}],"down_asks":[{"price":"0.10","size":"100"}]}
{"type":"snapshot","market_id":"m1","timestamp":"2026-05-14T12:00:10+00:00","time_to_resolve_s":5,"up_token_id":"u","down_token_id":"d","up_best_ask":"0.95","up_best_ask_size":"100","down_best_ask":"0.07","down_best_ask_size":"100","up_asks":[{"price":"0.95","size":"100"}],"down_asks":[{"price":"0.07","size":"100"}]}
{"type":"intent","intent_id":"i1","market_id":"m1","side":"up","notional_usdc":"1.00"}
{"type":"fill","intent_id":"i1","market_id":"m1","side":"up","shares":"1.0526","avg_price":"0.95","timestamp":"2026-05-14T12:00:10+00:00"}
{"type":"resolution","market_id":"m1","timestamp":"2026-05-14T12:00:15+00:00","winning_side":"up"}
```

`tests/test_historical_feed.py`:
```python
from decimal import Decimal
from pathlib import Path

import pytest

from polybot.feed.historical import HistoricalFeed
from polybot.types import MarketSnapshot, ResolutionEvent

FIXTURE = Path(__file__).parent / "fixtures" / "tiny_session.jsonl"


async def test_replays_snapshots_and_resolution_in_order():
    feed = HistoricalFeed(FIXTURE)
    events = [e async for e in feed.events()]
    # 2 snapshots + 1 resolution. Intents/fills in the file are ignored by the feed.
    assert len(events) == 3
    assert isinstance(events[0], MarketSnapshot)
    assert events[0].up_best_ask == Decimal("0.92")
    assert isinstance(events[1], MarketSnapshot)
    assert events[1].time_to_resolve_s == 5
    assert isinstance(events[2], ResolutionEvent)
    assert events[2].winning_side == "up"


async def test_missing_file_raises(tmp_path: Path):
    feed = HistoricalFeed(tmp_path / "nope.jsonl")
    with pytest.raises(FileNotFoundError):
        async for _ in feed.events():
            pass
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_historical_feed.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Create feed package init**

`src/polybot/feed/__init__.py`:
```python
```

- [ ] **Step 4: Implement DataFeed protocol**

`src/polybot/feed/base.py`:
```python
"""DataFeed interface. Yields MarketSnapshot and ResolutionEvent in order."""
from __future__ import annotations

from typing import AsyncIterator, Protocol

from polybot.types import FeedEvent


class DataFeed(Protocol):
    def events(self) -> AsyncIterator[FeedEvent]: ...
```

- [ ] **Step 5: Implement HistoricalFeed**

`src/polybot/feed/historical.py`:
```python
"""Replays a JSONL recording as a stream of FeedEvents.

Only `snapshot` and `resolution` lines are emitted. `intent` and `fill` lines
exist for audit and are skipped here — the strategy + executor in the replay
will produce their own.
"""
from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import AsyncIterator

from polybot.types import BookLevel, FeedEvent, MarketSnapshot, ResolutionEvent


def _parse_snapshot(raw: dict) -> MarketSnapshot:
    return MarketSnapshot(
        market_id=raw["market_id"],
        timestamp=datetime.fromisoformat(raw["timestamp"]),
        time_to_resolve_s=float(raw["time_to_resolve_s"]),
        up_token_id=raw["up_token_id"],
        down_token_id=raw["down_token_id"],
        up_best_ask=Decimal(raw["up_best_ask"]) if raw.get("up_best_ask") else None,
        up_best_ask_size=Decimal(raw["up_best_ask_size"])
        if raw.get("up_best_ask_size")
        else None,
        down_best_ask=Decimal(raw["down_best_ask"])
        if raw.get("down_best_ask")
        else None,
        down_best_ask_size=Decimal(raw["down_best_ask_size"])
        if raw.get("down_best_ask_size")
        else None,
        up_asks=[
            BookLevel(price=Decimal(l["price"]), size=Decimal(l["size"]))
            for l in raw.get("up_asks", [])
        ],
        down_asks=[
            BookLevel(price=Decimal(l["price"]), size=Decimal(l["size"]))
            for l in raw.get("down_asks", [])
        ],
    )


def _parse_resolution(raw: dict) -> ResolutionEvent:
    return ResolutionEvent(
        market_id=raw["market_id"],
        timestamp=datetime.fromisoformat(raw["timestamp"]),
        winning_side=raw["winning_side"],
    )


class HistoricalFeed:
    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)

    async def events(self) -> AsyncIterator[FeedEvent]:
        if not self._path.exists():
            raise FileNotFoundError(self._path)
        with self._path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                raw = json.loads(line)
                t = raw.get("type")
                if t == "snapshot":
                    yield _parse_snapshot(raw)
                elif t == "resolution":
                    yield _parse_resolution(raw)
                # intent/fill lines are intentionally skipped
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_historical_feed.py -v`
Expected: 2 passed

- [ ] **Step 7: Commit**

```bash
git add src/polybot/feed/__init__.py src/polybot/feed/base.py src/polybot/feed/historical.py tests/fixtures/tiny_session.jsonl tests/test_historical_feed.py
git commit -m "feat: data feed protocol + historical replay"
```

---

## Task 9: Runner

**Files:**
- Create: `src/polybot/runner.py`
- Test: `tests/test_runner_integration.py`

- [ ] **Step 1: Write the failing integration test**

`tests/test_runner_integration.py`:
```python
from decimal import Decimal
from pathlib import Path

from polybot.executor.paper import PaperExecutor
from polybot.feed.historical import HistoricalFeed
from polybot.portfolio import Portfolio
from polybot.recorder import Recorder
from polybot.runner import run_loop
from polybot.strategy.bot1 import Bot1Strategy

FIXTURE = Path(__file__).parent / "fixtures" / "tiny_session.jsonl"


async def test_replay_produces_expected_pnl(tmp_path: Path):
    feed = HistoricalFeed(FIXTURE)
    strategy = Bot1Strategy(
        price_band=(Decimal("0.85"), Decimal("0.99")),
        time_window_s=(1.0, 20.0),
        trade_size_usdc=Decimal("1.00"),
    )
    executor = PaperExecutor()
    portfolio = Portfolio(max_daily_trades=10, max_daily_loss_usdc=Decimal("10"))
    recorder = Recorder(dir=tmp_path)

    await run_loop(
        feed=feed,
        strategy=strategy,
        executor=executor,
        portfolio=portfolio,
        recorder=recorder,
    )

    # The fixture has two snapshots — both within window. First is at $0.92 (ttr=15),
    # second at $0.95 (ttr=5). Strategy buys on the first qualifying snapshot.
    # $1 → 1/0.92 shares. Winning side is "up". P&L = 1/0.92 - 1.
    expected = Decimal("1") / Decimal("0.92") - Decimal("1")
    assert portfolio.day_pnl == expected
    assert portfolio.day_trades == 1
    assert portfolio.holds_market("m1") is False  # resolved

    recorder.close()
    # Recorder wrote at least the resolution and the fill it observed.
    out = list(tmp_path.glob("*.jsonl"))
    assert len(out) == 1
    assert out[0].stat().st_size > 0


async def test_kill_switch_blocks_trades(tmp_path: Path):
    feed = HistoricalFeed(FIXTURE)
    strategy = Bot1Strategy(
        price_band=(Decimal("0.85"), Decimal("0.99")),
        time_window_s=(1.0, 20.0),
        trade_size_usdc=Decimal("1.00"),
    )
    executor = PaperExecutor()
    portfolio = Portfolio(max_daily_trades=10, max_daily_loss_usdc=Decimal("10"))
    portfolio.day_trades = 10  # already at the cap
    recorder = Recorder(dir=tmp_path)

    await run_loop(
        feed=feed,
        strategy=strategy,
        executor=executor,
        portfolio=portfolio,
        recorder=recorder,
    )

    assert portfolio.day_trades == 10  # unchanged: no trades executed
    recorder.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_runner_integration.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'polybot.runner'`

- [ ] **Step 3: Implement run_loop**

`src/polybot/runner.py`:
```python
"""Wires DataFeed → Strategy → Executor → Portfolio together.

Mode is purely a wiring choice: caller decides whether to pass LiveFeed or
HistoricalFeed, PaperExecutor or LiveExecutor.
"""
from __future__ import annotations

import logging
from typing import Protocol

from polybot.executor.base import Executor
from polybot.portfolio import Portfolio
from polybot.recorder import Recorder
from polybot.strategy.bot1 import Bot1Strategy
from polybot.types import FeedEvent, MarketSnapshot, ResolutionEvent

log = logging.getLogger(__name__)


class _Feed(Protocol):
    def events(self): ...  # AsyncIterator[FeedEvent]


class _SnapshotSink(Protocol):
    def on_snapshot(self, snap: MarketSnapshot) -> None: ...


async def run_loop(
    *,
    feed: _Feed,
    strategy: Bot1Strategy,
    executor: Executor,
    portfolio: Portfolio,
    recorder: Recorder,
) -> None:
    async for event in feed.events():
        if isinstance(event, MarketSnapshot):
            recorder.record_snapshot(event)
            # Feed the executor's in-memory book so submit() has prices to fill against.
            if isinstance(executor, _SnapshotSink) or hasattr(executor, "on_snapshot"):
                executor.on_snapshot(event)

            if portfolio.is_halted():
                log.debug("halted: skipping snapshot for %s", event.market_id)
                continue

            intent = strategy.decide(
                event, holds_market=portfolio.holds_market(event.market_id)
            )
            if intent is None:
                continue
            recorder.record_intent(intent)
            fill = await executor.submit(intent)
            if fill is None:
                log.info("intent %s did not fill", intent.intent_id)
                continue
            recorder.record_fill(fill)
            portfolio.apply_fill(fill)
            log.info(
                "filled %s %s shares @ %s on %s",
                fill.side,
                fill.shares,
                fill.avg_price,
                fill.market_id,
            )

        elif isinstance(event, ResolutionEvent):
            recorder.record_resolution(event)
            portfolio.apply_resolution(event)
            log.info(
                "resolved %s → %s, day P&L=%s",
                event.market_id,
                event.winning_side,
                portfolio.day_pnl,
            )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_runner_integration.py -v`
Expected: 2 passed

- [ ] **Step 5: Run full test suite**

Run: `pytest -v`
Expected: All tests pass (types, config, strategy, paper executor, portfolio, recorder, historical feed, runner integration).

- [ ] **Step 6: Commit**

```bash
git add src/polybot/runner.py tests/test_runner_integration.py
git commit -m "feat: runner wires feed/strategy/executor/portfolio"
```

---

## Task 10: Live Feed (Gamma + CLOB WebSocket)

**Note:** This is the only file in v1 that touches external services. We don't unit-test it because it's pure I/O glue. The known risk is that Gamma's slug/schema for the 5-min BTC market may differ from what we expect — we'll iterate when running `run_paper.py` for real.

**Files:**
- Create: `src/polybot/feed/live.py`

- [ ] **Step 1: Implement LiveFeed**

`src/polybot/feed/live.py`:
```python
"""LiveFeed: discovers the active 5-min BTC market via Gamma, subscribes to its
two outcome tokens via the CLOB WebSocket, and emits MarketSnapshots whenever
the top of book changes (plus a heartbeat every `heartbeat_interval_s`).

After the market's window ends, polls Gamma every `resolution_poll_interval_s`
until it reports resolved, then emits a ResolutionEvent and moves to the next
market.

Schema/slug assumptions live in `discover_active_market` and `_parse_market`.
If Polymarket returns a different shape than we expect, these are the methods
to adjust.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, AsyncIterator

import httpx
import websockets

from polybot.config import FeedConfig
from polybot.types import BookLevel, FeedEvent, MarketSnapshot, ResolutionEvent

log = logging.getLogger(__name__)


class LiveFeed:
    def __init__(self, cfg: FeedConfig) -> None:
        self._cfg = cfg

    async def events(self) -> AsyncIterator[FeedEvent]:
        async with httpx.AsyncClient(timeout=10.0) as http:
            while True:
                market = await self._discover_active_market(http)
                if market is None:
                    log.warning("no active market found; retrying in 10s")
                    await asyncio.sleep(10)
                    continue
                async for ev in self._stream_market(http, market):
                    yield ev

    async def _discover_active_market(
        self, http: httpx.AsyncClient
    ) -> dict[str, Any] | None:
        # Gamma API: /markets?active=true&closed=false&limit=100
        # We then filter by slug substring. The slug pattern for recurring
        # markets has historically looked like:
        #   bitcoin-up-or-down-may-14-2026-12pm-et
        # Adjust as needed if the live shape differs.
        url = f"{self._cfg.gamma_url}/markets"
        params = {"active": "true", "closed": "false", "limit": 100}
        resp = await http.get(url, params=params)
        resp.raise_for_status()
        for raw in resp.json():
            slug = raw.get("slug", "")
            if self._cfg.market_slug_substring in slug:
                return self._parse_market(raw)
        return None

    def _parse_market(self, raw: dict[str, Any]) -> dict[str, Any] | None:
        # Expect two outcome tokens; map them to up/down by name.
        tokens = raw.get("tokens") or raw.get("clobTokenIds") or []
        # Newer Gamma payloads use `outcomes` (list of names) + `clobTokenIds` (list of ids).
        outcomes = raw.get("outcomes", [])
        if outcomes and "clobTokenIds" in raw:
            token_map = dict(zip(outcomes, raw["clobTokenIds"]))
            up_id = token_map.get("Up") or token_map.get("up")
            down_id = token_map.get("Down") or token_map.get("down")
        else:
            up_id = down_id = None
            for t in tokens:
                name = (t.get("outcome") or t.get("name") or "").lower()
                if name == "up":
                    up_id = t.get("token_id") or t.get("id")
                elif name == "down":
                    down_id = t.get("token_id") or t.get("id")
        if not up_id or not down_id:
            log.warning("could not extract up/down token ids from market %s", raw.get("id"))
            return None
        end_iso = raw.get("endDateIso") or raw.get("end_date_iso") or raw.get("endDate")
        end_dt = datetime.fromisoformat(end_iso.replace("Z", "+00:00")) if end_iso else None
        return {
            "id": raw.get("id") or raw.get("conditionId"),
            "slug": raw.get("slug"),
            "up_token_id": str(up_id),
            "down_token_id": str(down_id),
            "end": end_dt,
        }

    async def _stream_market(
        self, http: httpx.AsyncClient, market: dict[str, Any]
    ) -> AsyncIterator[FeedEvent]:
        market_id = market["id"]
        end: datetime | None = market["end"]
        log.info("streaming market %s (end=%s)", market_id, end)

        # Track latest top-of-book per token.
        state = {
            "up": {"price": None, "size": None, "asks": []},
            "down": {"price": None, "size": None, "asks": []},
        }

        async def make_snapshot() -> MarketSnapshot:
            now = datetime.now(timezone.utc)
            ttr = (end - now).total_seconds() if end else 0.0
            return MarketSnapshot(
                market_id=market_id,
                timestamp=now,
                time_to_resolve_s=ttr,
                up_token_id=market["up_token_id"],
                down_token_id=market["down_token_id"],
                up_best_ask=state["up"]["price"],
                up_best_ask_size=state["up"]["size"],
                down_best_ask=state["down"]["price"],
                down_best_ask_size=state["down"]["size"],
                up_asks=list(state["up"]["asks"]),
                down_asks=list(state["down"]["asks"]),
            )

        # Seed both sides with REST book snapshots.
        for side, token_id in (
            ("up", market["up_token_id"]),
            ("down", market["down_token_id"]),
        ):
            try:
                resp = await http.get(
                    f"{self._cfg.clob_rest_url}/book",
                    params={"token_id": token_id},
                )
                resp.raise_for_status()
                _apply_book(state[side], resp.json())
            except Exception as exc:  # noqa: BLE001
                log.warning("initial book fetch failed for %s: %s", side, exc)

        # Subscribe over WebSocket.
        sub_msg = json.dumps(
            {
                "type": "market",
                "assets_ids": [market["up_token_id"], market["down_token_id"]],
            }
        )

        snapshot_queue: asyncio.Queue[FeedEvent] = asyncio.Queue()

        async def ws_task():
            try:
                async with websockets.connect(self._cfg.clob_ws_url) as ws:
                    await ws.send(sub_msg)
                    async for raw_msg in ws:
                        msg = json.loads(raw_msg)
                        token_id = msg.get("asset_id") or msg.get("token_id")
                        if token_id == market["up_token_id"]:
                            _apply_book(state["up"], msg)
                        elif token_id == market["down_token_id"]:
                            _apply_book(state["down"], msg)
                        await snapshot_queue.put(await make_snapshot())
            except Exception as exc:  # noqa: BLE001
                log.warning("ws stream ended: %s", exc)

        async def heartbeat_task():
            while True:
                await asyncio.sleep(self._cfg.heartbeat_interval_s)
                await snapshot_queue.put(await make_snapshot())
                if end and datetime.now(timezone.utc) > end:
                    return

        ws_handle = asyncio.create_task(ws_task())
        hb_handle = asyncio.create_task(heartbeat_task())

        try:
            while True:
                event = await snapshot_queue.get()
                yield event
                if end and datetime.now(timezone.utc) > end:
                    break
        finally:
            hb_handle.cancel()
            ws_handle.cancel()

        # Poll for resolution.
        while True:
            await asyncio.sleep(self._cfg.resolution_poll_interval_s)
            try:
                resp = await http.get(
                    f"{self._cfg.gamma_url}/markets/{market_id}"
                )
                resp.raise_for_status()
                raw = resp.json()
                if raw.get("closed") or raw.get("resolved"):
                    winning_side = _winning_side(raw)
                    if winning_side is not None:
                        yield ResolutionEvent(
                            market_id=market_id,
                            timestamp=datetime.now(timezone.utc),
                            winning_side=winning_side,
                        )
                        return
            except Exception as exc:  # noqa: BLE001
                log.warning("resolution poll failed: %s", exc)


def _apply_book(side_state: dict, msg: dict) -> None:
    """Update side_state in place from a CLOB book message.

    Accepts both REST snapshot shape ({"asks": [["0.90","100"], ...]}) and
    WebSocket diff/full shape. Tolerant of missing fields — silently no-ops.
    """
    asks = msg.get("asks") or []
    levels = []
    for entry in asks:
        if isinstance(entry, list) and len(entry) >= 2:
            price = Decimal(str(entry[0]))
            size = Decimal(str(entry[1]))
        elif isinstance(entry, dict):
            price = Decimal(str(entry.get("price")))
            size = Decimal(str(entry.get("size") or entry.get("amount")))
        else:
            continue
        if size > 0:
            levels.append(BookLevel(price=price, size=size))
    levels.sort(key=lambda l: l.price)
    side_state["asks"] = levels
    if levels:
        side_state["price"] = levels[0].price
        side_state["size"] = levels[0].size
    else:
        side_state["price"] = None
        side_state["size"] = None


def _winning_side(raw: dict) -> str | None:
    # Try common shapes for resolution payloads.
    outcome = raw.get("winning_outcome") or raw.get("winningOutcome")
    if isinstance(outcome, str):
        o = outcome.lower()
        if o in ("up", "down"):
            return o
    # Payouts: [1, 0] vs [0, 1] indexed by outcome order.
    payouts = raw.get("payouts") or raw.get("payoutNumerators")
    outcomes = raw.get("outcomes")
    if payouts and outcomes and len(payouts) == len(outcomes):
        for payout, name in zip(payouts, outcomes):
            try:
                p = float(payout)
            except (TypeError, ValueError):
                continue
            if p > 0:
                n = name.lower()
                if n in ("up", "down"):
                    return n
    return None
```

- [ ] **Step 2: Run lint to catch syntax issues**

Run: `ruff check src/polybot/feed/live.py`
Expected: No errors (warnings about broad-except are intentional and allowed via `# noqa`).

- [ ] **Step 3: Run full test suite to confirm nothing else broke**

Run: `pytest -v`
Expected: All previously-passing tests still pass.

- [ ] **Step 4: Commit**

```bash
git add src/polybot/feed/live.py
git commit -m "feat: live feed (Gamma discovery + CLOB websocket)"
```

---

## Task 11: Entry-point Scripts

**Files:**
- Create: `scripts/run_backtest.py`
- Create: `scripts/run_paper.py`

- [ ] **Step 1: Implement `scripts/run_backtest.py`**

```python
"""Replay a recorded session through Bot 1 and print summary P&L."""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from polybot.config import load_config
from polybot.executor.paper import PaperExecutor
from polybot.feed.historical import HistoricalFeed
from polybot.portfolio import Portfolio
from polybot.recorder import Recorder
from polybot.runner import run_loop
from polybot.strategy.bot1 import Bot1Strategy


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("recording", type=Path, help="JSONL recording to replay")
    parser.add_argument(
        "--config", type=Path, default=Path("config.yaml"), help="config file"
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    cfg = load_config(args.config)

    feed = HistoricalFeed(args.recording)
    strategy = Bot1Strategy(
        price_band=cfg.strategy.price_band,
        time_window_s=cfg.strategy.time_window_s,
        trade_size_usdc=cfg.strategy.trade_size_usdc,
    )
    executor = PaperExecutor()
    portfolio = Portfolio(
        max_daily_trades=cfg.risk.max_daily_trades,
        max_daily_loss_usdc=cfg.risk.max_daily_loss_usdc,
    )
    with Recorder(dir=cfg.recorder.dir) as recorder:
        await run_loop(
            feed=feed,
            strategy=strategy,
            executor=executor,
            portfolio=portfolio,
            recorder=recorder,
        )

    print(f"=== Backtest done ===")
    print(f"trades:    {portfolio.day_trades}")
    print(f"day P&L:   {portfolio.day_pnl}")
    print(f"total P&L: {portfolio.total_pnl}")
    print(f"open:      {len(portfolio.open_positions())}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
```

- [ ] **Step 2: Implement `scripts/run_paper.py`**

```python
"""Paper-trade Bot 1 against live Polymarket data. No real orders are placed.

v1 prints a running summary every N seconds and writes a JSONL recording for
later replay. Ctrl-C exits cleanly.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from polybot.config import load_config
from polybot.executor.paper import PaperExecutor
from polybot.feed.live import LiveFeed
from polybot.portfolio import Portfolio
from polybot.recorder import Recorder
from polybot.runner import run_loop
from polybot.strategy.bot1 import Bot1Strategy

SUMMARY_INTERVAL_S = 30.0


async def _periodic_summary(portfolio: Portfolio):
    while True:
        await asyncio.sleep(SUMMARY_INTERVAL_S)
        print(
            f"[summary] trades={portfolio.day_trades} "
            f"day_pnl={portfolio.day_pnl} "
            f"total_pnl={portfolio.total_pnl} "
            f"open={len(portfolio.open_positions())} "
            f"halted={portfolio.is_halted()}",
            flush=True,
        )


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config", type=Path, default=Path("config.yaml"), help="config file"
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    cfg = load_config(args.config)

    feed = LiveFeed(cfg.feed)
    strategy = Bot1Strategy(
        price_band=cfg.strategy.price_band,
        time_window_s=cfg.strategy.time_window_s,
        trade_size_usdc=cfg.strategy.trade_size_usdc,
    )
    executor = PaperExecutor()
    portfolio = Portfolio(
        max_daily_trades=cfg.risk.max_daily_trades,
        max_daily_loss_usdc=cfg.risk.max_daily_loss_usdc,
    )

    with Recorder(dir=cfg.recorder.dir) as recorder:
        summary = asyncio.create_task(_periodic_summary(portfolio))
        try:
            await run_loop(
                feed=feed,
                strategy=strategy,
                executor=executor,
                portfolio=portfolio,
                recorder=recorder,
            )
        finally:
            summary.cancel()

    print("=== Paper run done ===")
    print(f"trades:    {portfolio.day_trades}")
    print(f"day P&L:   {portfolio.day_pnl}")
    print(f"total P&L: {portfolio.total_pnl}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        print("\ninterrupted")
        sys.exit(0)
```

- [ ] **Step 3: Verify scripts import cleanly**

Run: `python -c "import scripts.run_backtest, scripts.run_paper"`

If that fails because `scripts` isn't a package, instead run:
```bash
python scripts/run_backtest.py --help
python scripts/run_paper.py --help
```
Expected: argparse help text prints, no import errors.

- [ ] **Step 4: Run backtest against fixture as a smoke test**

Run:
```bash
python scripts/run_backtest.py tests/fixtures/tiny_session.jsonl
```
Expected:
```
=== Backtest done ===
trades:    1
day P&L:   0.0869565217391304347826086957...
total P&L: 0.0869565217391304347826086957...
open:      0
```

- [ ] **Step 5: Commit**

```bash
git add scripts/run_backtest.py scripts/run_paper.py
git commit -m "feat: entry-point scripts (paper + backtest)"
```

---

## Task 12: Final Lint + Full Test Sweep

- [ ] **Step 1: Run ruff**

Run: `ruff check src tests scripts`
Expected: No errors. Fix anything reported.

- [ ] **Step 2: Run full test suite**

Run: `pytest -v`
Expected: All tests pass.

- [ ] **Step 3: Update README with verified-working commands**

Confirm the README's "Run" and "Test" sections still match reality. If anything drifted (e.g. command syntax), edit `README.md` to match.

- [ ] **Step 4: Commit any cleanup**

```bash
git add -A
git commit -m "chore: lint + final test pass" || true
```

---

## Notes on Live Run (Manual Verification, Not Automated)

After Task 12, the bot is ready for a real paper run. Because the live Gamma slug pattern is the most fragile part of the stack:

1. Run `python scripts/run_paper.py` for ~10 minutes during US market hours when a 5-min BTC market is active.
2. If `LiveFeed._discover_active_market` logs "no active market found" repeatedly, hit `https://gamma-api.polymarket.com/markets?active=true&closed=false&limit=100` directly and inspect the returned slugs. Adjust `feed.market_slug_substring` in `config.yaml`, or tweak `_parse_market` to match the live schema.
3. Watch the `[summary]` lines and the per-resolution log lines. The kill switches will stop the bot if `max_daily_trades` or `max_daily_loss_usdc` is breached — even though it's paper, the same code paths run, which is the point.
4. After a session, the JSONL in `recordings/` can be replayed via `run_backtest.py` to confirm deterministic behavior.

**No live execution code ships in v1.** `LiveExecutor` does not exist as a class — paper mode is the only executor. v2 will add it as a separate spec + plan.
