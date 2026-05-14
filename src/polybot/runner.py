"""Wires DataFeed → Strategy → Executor → Portfolio together.

Mode is purely a wiring choice: caller decides whether to pass LiveFeed or
HistoricalFeed, PaperExecutor or LiveExecutor.
"""
from __future__ import annotations

import logging
from typing import Protocol

from polybot.executor.base import Executor
from polybot.portfolio import Portfolio
from polybot.recorder import Recorder
from polybot.strategy.bot1 import Bot1Strategy
from polybot.types import MarketSnapshot, ResolutionEvent

log = logging.getLogger(__name__)


class _Feed(Protocol):
    def events(self): ...  # AsyncIterator[FeedEvent]


async def run_loop(
    *,
    feed: _Feed,
    strategy: Bot1Strategy,
    executor: Executor,
    portfolio: Portfolio,
    recorder: Recorder,
) -> None:
    async for event in feed.events():
        if isinstance(event, MarketSnapshot):
            recorder.record_snapshot(event)
            # Feed the executor's in-memory book so submit() has prices to fill against.
            if hasattr(executor, "on_snapshot"):
                executor.on_snapshot(event)

            if portfolio.is_halted():
                log.debug("halted: skipping snapshot for %s", event.market_id)
                continue

            position = portfolio.get_position(event.market_id)
            # Strategies that don't care about `position` ignore the kwarg.
            try:
                intent = strategy.decide(
                    event,
                    holds_market=position is not None,
                    position=position,
                )
            except TypeError:
                intent = strategy.decide(
                    event, holds_market=position is not None
                )
            if intent is None:
                continue
            recorder.record_intent(intent)
            fill = await executor.submit(intent)
            if fill is None:
                log.info("intent %s did not fill", intent.intent_id)
                continue
            recorder.record_fill(fill)
            portfolio.apply_fill(fill)
            log.info(
                "%s %s %s shares @ %s on %s",
                "sold" if fill.action == "sell" else "filled",
                fill.side,
                fill.shares,
                fill.avg_price,
                fill.market_id,
            )

        elif isinstance(event, ResolutionEvent):
            recorder.record_resolution(event)
            portfolio.apply_resolution(event)
            log.info(
                "resolved %s → %s, day P&L=%s",
                event.market_id,
                event.winning_side,
                portfolio.day_pnl,
            )
