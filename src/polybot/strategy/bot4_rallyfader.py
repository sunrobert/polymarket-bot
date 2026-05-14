"""Bot 4: Rally Fader. The pessimistic mirror of Bot 3.

Bot 3 buys Up when Up dips, betting on a bounce.
Bot 4 buys Down when Down dips (i.e., Up has rallied hard), betting that the
rally gives back. Same mean-reversion thesis, opposite side of the book.

Running both side by side answers: is the bounce edge directional (only works
when Up is the dip side) or symmetric (works equally on either side)?
"""
from __future__ import annotations

import uuid
from decimal import Decimal

from polybot.types import MarketSnapshot, Position, TradeIntent


class Bot4RallyFaderStrategy:
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
        # Exit path: already long Down; check implied Down bid (1 - Up ask).
        if position is not None:
            if position.side != "down" or position.shares <= 0:
                return None
            if snapshot.up_best_ask is None:
                return None
            implied_down_bid = Decimal("1") - snapshot.up_best_ask
            if implied_down_bid >= self.exit_price:
                return TradeIntent(
                    intent_id=str(uuid.uuid4()),
                    market_id=snapshot.market_id,
                    side="down",
                    notional_usdc=Decimal("0"),
                    action="sell",
                    shares=position.shares,
                    limit_price=self.exit_price,
                )
            return None

        # Entry path: only buy if not already in this market.
        if holds_market:
            return None
        if snapshot.down_best_ask is None:
            return None
        if snapshot.down_best_ask > self.entry_price:
            return None
        return TradeIntent(
            intent_id=str(uuid.uuid4()),
            market_id=snapshot.market_id,
            side="down",
            notional_usdc=self.trade_size_usdc,
            action="buy",
            limit_price=self.entry_price,
        )
