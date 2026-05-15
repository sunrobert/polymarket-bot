"""Bot 7: Speculation Dip Buyer. Bot 3 + time-window discipline.

Thesis: the first ~half of a 5-minute BTC binary market is dominated by
speculative noise (thin books, retail FOMO/panic) and contracts overshoot
fair value. The final stretch is dominated by smart-money pinning as the
outcome becomes near-knowable from spot. The exploitable window is
"buy fear early, sell as smart money arrives, get out before convergence."

Concretely:
  - Entry: same as Bot 3 (Up ask <= entry_price), but ONLY when
    time_to_resolve_s > entry_cutoff_s. Past that, we're trading against
    smart money on a knowable outcome.
  - Profit exit: same as Bot 3 (implied Up bid >= exit_price, Limit GTC).
  - Hard time stop: if time_to_resolve_s <= force_exit_s and we still hold,
    SELL AT MARKET — take whatever the book offers. The goal is to avoid
    binary resolution risk where the contract may go to $0.

This converts the previous "all-or-nothing at resolution" tail risk into a
bounded "whatever the book gives us at T-2:30" loss, in exchange for capping
the windfall when a held contract would have resolved Up.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

from polybot.types import MarketSnapshot, Position, TradeIntent


class Bot7SpeculationStrategy:
    def __init__(
        self,
        entry_price: Decimal,
        exit_price: Decimal,
        trade_size_usdc: Decimal,
        entry_cutoff_s: float = 150.0,
        force_exit_s: float = 150.0,
    ) -> None:
        if entry_price <= 0 or entry_price >= exit_price:
            raise ValueError(
                f"need 0 < entry_price < exit_price, got {entry_price}/{exit_price}"
            )
        if entry_cutoff_s <= 0 or force_exit_s <= 0:
            raise ValueError("entry_cutoff_s and force_exit_s must be > 0")
        self.entry_price = entry_price
        self.exit_price = exit_price
        self.trade_size_usdc = trade_size_usdc
        self.entry_cutoff_s = entry_cutoff_s
        self.force_exit_s = force_exit_s

    def decide(
        self,
        snapshot: MarketSnapshot,
        holds_market: bool,
        position: Position | None = None,
    ) -> TradeIntent | None:
        # Hard time-stop takes priority over normal exit and is unconditional —
        # we want OUT before the market converges to truth.
        if position is not None and position.shares > 0:
            if snapshot.time_to_resolve_s <= self.force_exit_s:
                return TradeIntent(
                    intent_id=str(uuid.uuid4()),
                    market_id=snapshot.market_id,
                    side=position.side,
                    notional_usdc=Decimal("0"),
                    action="sell",
                    shares=position.shares,
                    limit_price=None,  # market sell: walk the book, take any price
                )

        # Normal profit exit: same as Bot 3.
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
                    limit_price=self.exit_price,
                )
            return None

        # Entry path. Restricted to the early speculation window.
        if holds_market:
            return None
        if snapshot.time_to_resolve_s <= self.entry_cutoff_s:
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
            limit_price=self.entry_price,
        )
