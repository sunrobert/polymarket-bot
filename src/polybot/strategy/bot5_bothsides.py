"""Bot 5: BothSides Dip Buyer. The union of Bot 3 and Bot 4 in a single bot.

Buys whichever side dips to entry_price first; sells when that side's implied
bid recovers to exit_price. One position per market max — same direction stays
in until exit triggers or market resolves.

Compared to running Bot 3 + Bot 4 separately:
- Same trades, but one process / one P&L / one recording instead of two.
- The downside: on a market where both sides oscillate through $0.35 within
  the window, this bot can only catch one of them (whichever it enters first).
"""
from __future__ import annotations

import uuid
from decimal import Decimal

from polybot.types import MarketSnapshot, Position, TradeIntent


class Bot5BothSidesStrategy:
    def __init__(
        self,
        entry_price: Decimal,
        exit_price: Decimal,
        trade_size_usdc: Decimal,
    ) -> None:
        if entry_price <= 0 or entry_price >= exit_price:
            raise ValueError(
                f"need 0 < entry_price < exit_price, got {entry_price}/{exit_price}"
            )
        self.entry_price = entry_price
        self.exit_price = exit_price
        self.trade_size_usdc = trade_size_usdc

    def decide(
        self,
        snapshot: MarketSnapshot,
        holds_market: bool,
        position: Position | None = None,
    ) -> TradeIntent | None:
        # Exit path: implied bid for whichever side we hold = 1 - opposite ask.
        if position is not None:
            if position.shares <= 0:
                return None
            opposite_ask = (
                snapshot.down_best_ask if position.side == "up" else snapshot.up_best_ask
            )
            if opposite_ask is None:
                return None
            implied_bid = Decimal("1") - opposite_ask
            if implied_bid >= self.exit_price:
                return TradeIntent(
                    intent_id=str(uuid.uuid4()),
                    market_id=snapshot.market_id,
                    side=position.side,
                    notional_usdc=Decimal("0"),
                    action="sell",
                    shares=position.shares,
                    limit_price=self.exit_price,
                )
            return None

        # Entry path: only buy if not already in this market.
        if holds_market:
            return None
        up_in = (
            snapshot.up_best_ask is not None
            and snapshot.up_best_ask <= self.entry_price
        )
        down_in = (
            snapshot.down_best_ask is not None
            and snapshot.down_best_ask <= self.entry_price
        )
        # Both in band means the book is broken or both are crashing — skip.
        # Neither in band is the common case.
        if up_in == down_in:
            return None
        side = "up" if up_in else "down"
        return TradeIntent(
            intent_id=str(uuid.uuid4()),
            market_id=snapshot.market_id,
            side=side,
            notional_usdc=self.trade_size_usdc,
            action="buy",
            limit_price=self.entry_price,
        )
