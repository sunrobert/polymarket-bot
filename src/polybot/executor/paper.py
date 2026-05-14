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

        if intent.action == "sell":
            return self._fill_sell(intent, snap)

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
            # Limit-price enforcement: refuse to pay more than limit_price.
            # Stops walking the book at the first level that would violate.
            if intent.limit_price is not None and level.price > intent.limit_price:
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

        if intent.limit_price is not None:
            # Limit orders: any partial fill within limit is a fill.
            if total_shares <= 0:
                return None
        elif remaining > 0:
            # Market orders: all-or-nothing.
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
            action="buy",
        )

    def _fill_sell(self, intent: TradeIntent, snap: MarketSnapshot) -> Fill | None:
        # For a binary, implied bids for `side` come from the opposite side's
        # asks: bid_price = 1 - opp_ask_price, bid_size = opp_ask_size.
        # Best bid is the lowest opposite ask. Walk worst-to-best is unusual;
        # we walk best (highest bid) first by reading opposite asks low-to-high.
        opp_asks = self._asks_for(snap, "down" if intent.side == "up" else "up")
        if not opp_asks:
            return None
        shares_to_sell = intent.shares
        if shares_to_sell is None or shares_to_sell <= 0:
            return None

        remaining = shares_to_sell
        total_shares = Decimal("0")
        total_proceeds = Decimal("0")
        levels_touched = 0
        last_price: Decimal | None = None

        for level in opp_asks:
            if remaining <= 0:
                break
            bid_price = Decimal("1") - level.price
            if bid_price <= 0:
                continue
            # Limit-price enforcement: refuse to sell below limit_price.
            if intent.limit_price is not None and bid_price < intent.limit_price:
                break
            bid_size = level.size
            levels_touched += 1
            last_price = bid_price
            if bid_size >= remaining:
                total_shares += remaining
                total_proceeds += remaining * bid_price
                remaining = Decimal("0")
                break
            total_shares += bid_size
            total_proceeds += bid_size * bid_price
            remaining -= bid_size

        if total_shares <= 0:
            return None
        # Partial fills allowed for sells: report what we got.
        avg_price = last_price if levels_touched == 1 else total_proceeds / total_shares
        return Fill(
            intent_id=intent.intent_id,
            market_id=intent.market_id,
            side=intent.side,
            shares=total_shares,
            avg_price=avg_price,
            timestamp=snap.timestamp,
            action="sell",
        )

    @staticmethod
    def _asks_for(snap: MarketSnapshot, side: Side) -> list[BookLevel]:
        return snap.up_asks if side == "up" else snap.down_asks
