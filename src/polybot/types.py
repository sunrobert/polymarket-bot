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
    # BTC reference prices for strategies that need an external oracle.
    # btc_price = latest BTC/USD from Coinbase at snapshot time.
    # btc_open_price = BTC/USD at the market's eventStartTime (frozen per market).
    # Both None if the feed wasn't configured to provide them — Bot 1 ignores them,
    # Bot 2 requires them and skips the snapshot if absent.
    btc_price: Decimal | None = None
    btc_open_price: Decimal | None = None


@dataclass(frozen=True)
class ResolutionEvent:
    market_id: str
    timestamp: datetime
    winning_side: Side


FeedEvent = Union[MarketSnapshot, ResolutionEvent]


Action = Literal["buy", "sell"]


@dataclass(frozen=True)
class TradeIntent:
    intent_id: str
    market_id: str
    side: Side
    notional_usdc: Decimal
    action: Action = "buy"
    # For sells, optional shares-to-close. None means close full position.
    shares: Decimal | None = None


@dataclass(frozen=True)
class Fill:
    intent_id: str
    market_id: str
    side: Side
    shares: Decimal
    avg_price: Decimal
    timestamp: datetime
    action: Action = "buy"


@dataclass
class Position:
    market_id: str
    side: Side
    shares: Decimal
    cost_usdc: Decimal
    opened_at: datetime
    resolved: bool = False
    pnl_usdc: Decimal | None = None
