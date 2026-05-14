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
        total_cost = Decimal("0")
        levels_touched = 0
        last_price: Decimal | None = None

        for level in asks:
            if remaining <= 0:
                break
            level_notional = level.price * level.size
            levels_touched += 1
            last_price = level.price
            if level_notional >= remaining:
                shares_here = remaining / level.price
                total_shares += shares_here
                total_cost += remaining
                remaining = Decimal("0")
                break
            total_shares += level.size
            total_cost += level_notional
            remaining -= level_notional

        if remaining > 0:
            # Not enough liquidity to fill the intent at any price.
            return None

        # If only one level was touched, avg_price is exactly that level's price.
        # Avoids Decimal round-trip precision drift (e.g. 1/0.90 then 1/(1/0.90)).
        avg_price = last_price if levels_touched == 1 else total_cost / total_shares
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
