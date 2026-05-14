"""Portfolio: positions, fills, resolutions, kill switches. No I/O."""
from __future__ import annotations

from decimal import Decimal

from polybot.types import Fill, Position, ResolutionEvent


class Portfolio:
    def __init__(
        self, max_daily_trades: int, max_daily_loss_usdc: Decimal
    ) -> None:
        self._max_daily_trades = max_daily_trades
        self._max_daily_loss_usdc = max_daily_loss_usdc
        self._positions: dict[str, Position] = {}
        self.day_trades: int = 0
        self.day_pnl: Decimal = Decimal("0")
        self.total_pnl: Decimal = Decimal("0")

    def holds_market(self, market_id: str) -> bool:
        pos = self._positions.get(market_id)
        return pos is not None and not pos.resolved

    def get_position(self, market_id: str):
        pos = self._positions.get(market_id)
        if pos is None or pos.resolved:
            return None
        return pos

    def apply_fill(self, fill: Fill) -> None:
        if fill.action == "sell":
            pos = self._positions.get(fill.market_id)
            if pos is None or pos.resolved:
                return
            proceeds = fill.shares * fill.avg_price
            # Pro-rata cost basis for the shares being sold.
            cost_share = pos.cost_usdc * (fill.shares / pos.shares) if pos.shares > 0 else Decimal("0")
            pnl = proceeds - cost_share
            self.day_pnl += pnl
            self.total_pnl += pnl
            remaining_shares = pos.shares - fill.shares
            if remaining_shares <= Decimal("0"):
                pos.resolved = True
                pos.pnl_usdc = (pos.pnl_usdc or Decimal("0")) + pnl
                pos.shares = Decimal("0")
                pos.cost_usdc = Decimal("0")
            else:
                pos.shares = remaining_shares
                pos.cost_usdc -= cost_share
                pos.pnl_usdc = (pos.pnl_usdc or Decimal("0")) + pnl
            self.day_trades += 1
            return

        cost = fill.shares * fill.avg_price
        self._positions[fill.market_id] = Position(
            market_id=fill.market_id,
            side=fill.side,
            shares=fill.shares,
            cost_usdc=cost,
            opened_at=fill.timestamp,
        )
        self.day_trades += 1

    def apply_resolution(self, event: ResolutionEvent) -> None:
        pos = self._positions.get(event.market_id)
        if pos is None or pos.resolved:
            return
        payout = pos.shares if pos.side == event.winning_side else Decimal("0")
        pnl = payout - pos.cost_usdc
        pos.resolved = True
        pos.pnl_usdc = pnl
        self.day_pnl += pnl
        self.total_pnl += pnl

    def is_halted(self) -> bool:
        if self.day_trades >= self._max_daily_trades:
            return True
        if self.day_pnl <= -self._max_daily_loss_usdc:
            return True
        return False

    def open_positions(self) -> list[Position]:
        return [p for p in self._positions.values() if not p.resolved]
