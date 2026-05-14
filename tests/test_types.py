from datetime import datetime, timezone
from decimal import Decimal

from polybot.types import (
    BookLevel,
    Fill,
    MarketSnapshot,
    Position,
    ResolutionEvent,
    TradeIntent,
)


def _ts():
    return datetime(2026, 5, 14, 12, 0, 0, tzinfo=timezone.utc)


def test_market_snapshot_holds_book_state():
    snap = MarketSnapshot(
        market_id="m1",
        timestamp=_ts(),
        time_to_resolve_s=10.0,
        up_token_id="u",
        down_token_id="d",
        up_best_ask=Decimal("0.90"),
        up_best_ask_size=Decimal("100"),
        down_best_ask=Decimal("0.12"),
        down_best_ask_size=Decimal("100"),
        up_asks=[BookLevel(price=Decimal("0.90"), size=Decimal("100"))],
        down_asks=[BookLevel(price=Decimal("0.12"), size=Decimal("100"))],
    )
    assert snap.up_best_ask == Decimal("0.90")
    assert snap.up_asks[0].size == Decimal("100")


def test_resolution_event_winning_side():
    ev = ResolutionEvent(market_id="m1", timestamp=_ts(), winning_side="up")
    assert ev.winning_side == "up"


def test_trade_intent_carries_size():
    intent = TradeIntent(
        intent_id="i1", market_id="m1", side="up", notional_usdc=Decimal("1.00")
    )
    assert intent.notional_usdc == Decimal("1.00")


def test_fill_round_trip():
    fill = Fill(
        intent_id="i1",
        market_id="m1",
        side="up",
        shares=Decimal("1.111111"),
        avg_price=Decimal("0.90"),
        timestamp=_ts(),
    )
    assert fill.shares * fill.avg_price <= Decimal("1.00")


def test_position_defaults_unresolved():
    pos = Position(
        market_id="m1",
        side="up",
        shares=Decimal("1.1"),
        cost_usdc=Decimal("1.00"),
        opened_at=_ts(),
    )
    assert pos.resolved is False
    assert pos.pnl_usdc is None
