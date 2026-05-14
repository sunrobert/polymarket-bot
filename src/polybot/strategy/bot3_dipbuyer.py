"""Bot 3: Dip Buyer. Buy Up when ask drops to entry_price, sell when bid recovers.

Mean-reversion / overreaction bounce play. Stateless — relies on Portfolio for
current position info via the optional `position` kwarg passed by the runner.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

from polybot.types import MarketSnapshot, Position, TradeIntent


class Bot3DipBuyerStrategy:
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
        # Exit path: already long Up; check implied Up bid (1 - Down ask) vs exit.
        if position is not None:
            if position.side != "up" or position.shares <= 0:
                return None
            if snapshot.down_best_ask is None:
                return None
            implied_up_bid = Decimal("1") - snapshot.down_best_ask
            if implied_up_bid >= self.exit_price:
                return TradeIntent(
                    intent_id=str(uuid.uuid4()),
                    market_id=snapshot.market_id,
                    side="up",
                    notional_usdc=Decimal("0"),
                    action="sell",
                    shares=position.shares,
                )
            return None

        # Entry path: only buy if not already in this market.
        if holds_market:
            return None
        if snapshot.up_best_ask is None:
            return None
        if snapshot.up_best_ask > self.entry_price:
            return None
        return TradeIntent(
            intent_id=str(uuid.uuid4()),
            market_id=snapshot.market_id,
            side="up",
            notional_usdc=self.trade_size_usdc,
            action="buy",
        )
