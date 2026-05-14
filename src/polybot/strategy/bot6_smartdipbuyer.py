"""Bot 6: Smart Dip Buyer. Bot 3 + per-market price history filters.

Same dip-buying mechanic as Bot 3 (buy Up at <= entry_price, sell at >= exit_price)
but adds two filters on entry to avoid catching falling knives and to confirm
the bounce has started:

  1. Crash filter — skip entry if current Up ask < session_high * (1 - max_dip_pct).
     Default 50% — refuses to enter if Up has more than halved from its peak in
     this market. Big drops are usually real moves, not overreactions.

  2. Momentum confirmation — last N snapshots' Up asks must be monotonically
     non-decreasing AND show net positive growth (history[-1] > history[0]).
     Default N=5. Catches the bounce as it's happening, not while still falling.

This strategy is stateful: it maintains per-market session high and recent-price
deques. State persists across snapshots for the strategy instance's lifetime.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

from polybot.types import MarketSnapshot, Position, TradeIntent


class Bot6SmartDipBuyerStrategy:
    def __init__(
        self,
        entry_price: Decimal,
        exit_price: Decimal,
        trade_size_usdc: Decimal,
        max_dip_pct: Decimal = Decimal("0.50"),
        growth_window: int = 5,
    ) -> None:
        if entry_price <= 0 or entry_price >= exit_price:
            raise ValueError(
                f"need 0 < entry_price < exit_price, got {entry_price}/{exit_price}"
            )
        if not (Decimal("0") < max_dip_pct < Decimal("1")):
            raise ValueError(f"max_dip_pct must be in (0, 1), got {max_dip_pct}")
        if growth_window < 2:
            raise ValueError(f"growth_window must be >= 2, got {growth_window}")
        self.entry_price = entry_price
        self.exit_price = exit_price
        self.trade_size_usdc = trade_size_usdc
        self.max_dip_pct = max_dip_pct
        self.growth_window = growth_window
        # Per-market state.
        self._session_high: dict[str, Decimal] = {}
        self._recent_ups: dict[str, list[Decimal]] = {}

    def decide(
        self,
        snapshot: MarketSnapshot,
        holds_market: bool,
        position: Position | None = None,
    ) -> TradeIntent | None:
        # Always update history first so exit-path snapshots also contribute
        # to the session high (useful when we re-enter after exit).
        if snapshot.up_best_ask is not None:
            self._update_history(snapshot.market_id, snapshot.up_best_ask)

        # Exit path: same as Bot 3.
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

        # Entry path.
        if holds_market:
            return None
        if snapshot.up_best_ask is None:
            return None
        if snapshot.up_best_ask > self.entry_price:
            return None
        if not self._passes_crash_filter(snapshot.market_id, snapshot.up_best_ask):
            return None
        if not self._passes_momentum_filter(snapshot.market_id):
            return None
        return TradeIntent(
            intent_id=str(uuid.uuid4()),
            market_id=snapshot.market_id,
            side="up",
            notional_usdc=self.trade_size_usdc,
            action="buy",
            limit_price=self.entry_price,
        )

    def _update_history(self, market_id: str, up_ask: Decimal) -> None:
        prev_high = self._session_high.get(market_id)
        if prev_high is None or up_ask > prev_high:
            self._session_high[market_id] = up_ask
        history = self._recent_ups.setdefault(market_id, [])
        history.append(up_ask)
        if len(history) > self.growth_window:
            del history[: len(history) - self.growth_window]

    def _passes_crash_filter(self, market_id: str, up_ask: Decimal) -> bool:
        high = self._session_high.get(market_id)
        if high is None:
            return True
        floor = high * (Decimal("1") - self.max_dip_pct)
        return up_ask >= floor

    def _passes_momentum_filter(self, market_id: str) -> bool:
        history = self._recent_ups.get(market_id, [])
        if len(history) < self.growth_window:
            return False
        for i in range(1, len(history)):
            if history[i] < history[i - 1]:
                return False
        return history[-1] > history[0]
