from datetime import datetime, timezone
from decimal import Decimal

from polybot.strategy.bot5_bothsides import Bot5BothSidesStrategy
from polybot.types import BookLevel, MarketSnapshot, Position


def _snap(*, up_ask: Decimal, down_ask: Decimal) -> MarketSnapshot:
    return MarketSnapshot(
        market_id="m1",
        timestamp=datetime(2026, 5, 14, 12, 0, 0, tzinfo=timezone.utc),
        time_to_resolve_s=120.0,
        up_token_id="u",
        down_token_id="d",
        up_best_ask=up_ask,
        up_best_ask_size=Decimal("100"),
        down_best_ask=down_ask,
        down_best_ask_size=Decimal("100"),
        up_asks=[BookLevel(price=up_ask, size=Decimal("100"))],
        down_asks=[BookLevel(price=down_ask, size=Decimal("100"))],
    )


def _strategy() -> Bot5BothSidesStrategy:
    return Bot5BothSidesStrategy(
        entry_price=Decimal("0.35"),
        exit_price=Decimal("0.55"),
        trade_size_usdc=Decimal("5.00"),
    )


def _position(side: str, shares: Decimal = Decimal("14.29")) -> Position:
    return Position(
        market_id="m1",
        side=side,  # type: ignore[arg-type]
        shares=shares,
        cost_usdc=Decimal("5.00"),
        opened_at=datetime(2026, 5, 14, 12, 0, 0, tzinfo=timezone.utc),
    )


def test_buys_up_when_up_dips():
    s = _strategy()
    snap = _snap(up_ask=Decimal("0.35"), down_ask=Decimal("0.65"))
    intent = s.decide(snap, holds_market=False, position=None)
    assert intent is not None
    assert intent.side == "up"
    assert intent.action == "buy"
    assert intent.limit_price == Decimal("0.35")


def test_buys_down_when_down_dips():
    s = _strategy()
    snap = _snap(up_ask=Decimal("0.65"), down_ask=Decimal("0.35"))
    intent = s.decide(snap, holds_market=False, position=None)
    assert intent is not None
    assert intent.side == "down"
    assert intent.action == "buy"
    assert intent.limit_price == Decimal("0.35")


def test_skips_when_neither_side_dips():
    s = _strategy()
    snap = _snap(up_ask=Decimal("0.50"), down_ask=Decimal("0.50"))
    assert s.decide(snap, holds_market=False, position=None) is None


def test_skips_when_both_sides_in_band():
    # Pathological book: both sides cheap. Skip rather than guess.
    s = _strategy()
    snap = _snap(up_ask=Decimal("0.30"), down_ask=Decimal("0.30"))
    assert s.decide(snap, holds_market=False, position=None) is None


def test_sells_up_position_when_up_implied_bid_at_exit():
    # Holding Up; implied Up bid = 1 - 0.45 = 0.55
    s = _strategy()
    snap = _snap(up_ask=Decimal("0.55"), down_ask=Decimal("0.45"))
    pos = _position("up")
    intent = s.decide(snap, holds_market=True, position=pos)
    assert intent is not None
    assert intent.action == "sell"
    assert intent.side == "up"
    assert intent.limit_price == Decimal("0.55")


def test_sells_down_position_when_down_implied_bid_at_exit():
    # Holding Down; implied Down bid = 1 - 0.45 = 0.55
    s = _strategy()
    snap = _snap(up_ask=Decimal("0.45"), down_ask=Decimal("0.55"))
    pos = _position("down")
    intent = s.decide(snap, holds_market=True, position=pos)
    assert intent is not None
    assert intent.action == "sell"
    assert intent.side == "down"
    assert intent.limit_price == Decimal("0.55")


def test_holds_when_implied_bid_below_exit():
    s = _strategy()
    snap = _snap(up_ask=Decimal("0.50"), down_ask=Decimal("0.50"))
    pos = _position("up")
    assert s.decide(snap, holds_market=True, position=pos) is None
