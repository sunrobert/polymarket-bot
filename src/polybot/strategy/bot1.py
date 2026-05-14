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
