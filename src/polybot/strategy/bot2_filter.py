"""Bot 2 (filter version).

Same trade shape as Bot 1 — buy a heavy favorite in the closing seconds — but
adds a safety filter: only trade when the in-band side AGREES with BTC's
direction since the market opened. If Up is at $0.92 but BTC has *fallen* from
open, skip the trade (the market is mispriced and we're on the wrong side of it).

This version cannot generate alpha by itself; it removes the worst losses from
Bot 1's trade set. The signal version (bot2_signal) actually trades because of
oracle disagreement.

Bot 2 also uses a tighter band [0.85, 0.95] and a tighter window [5, 20]s than
Bot 1 — the user's explicit spec.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

from polybot.types import MarketSnapshot, Side, TradeIntent


class Bot2FilterStrategy:
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

        # Require external BTC reference. No reference → no trade.
        if snapshot.btc_price is None or snapshot.btc_open_price is None:
            return None

        lo_p, hi_p = self.price_band
        up_in = (
            snapshot.up_best_ask is not None and lo_p <= snapshot.up_best_ask <= hi_p
        )
        down_in = (
            snapshot.down_best_ask is not None
            and lo_p <= snapshot.down_best_ask <= hi_p
        )
        # Same ambiguity rule as Bot 1: exactly one side in band.
        if up_in == down_in:
            return None

        side: Side = "up" if up_in else "down"
        btc_up = snapshot.btc_price >= snapshot.btc_open_price

        # Direction must agree with the in-band side.
        if side == "up" and not btc_up:
            return None
        if side == "down" and btc_up:
            return None

        return TradeIntent(
            intent_id=str(uuid.uuid4()),
            market_id=snapshot.market_id,
            side=side,
            notional_usdc=self.trade_size_usdc,
        )
