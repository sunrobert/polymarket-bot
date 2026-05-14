from datetime import datetime, timezone
from decimal import Decimal

from polybot.strategy.bot4_rallyfader import Bot4RallyFaderStrategy
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


def _strategy() -> Bot4RallyFaderStrategy:
    return Bot4RallyFaderStrategy(
        entry_price=Decimal("0.35"),
        exit_price=Decimal("0.55"),
        trade_size_usdc=Decimal("5.00"),
    )


def _position(shares: Decimal = Decimal("14.29")) -> Position:
    return Position(
        market_id="m1",
        side="down",
        shares=shares,
        cost_usdc=Decimal("5.00"),
        opened_at=datetime(2026, 5, 14, 12, 0, 0, tzinfo=timezone.utc),
    )


def test_buys_down_when_down_ask_at_entry():
    s = _strategy()
    snap = _snap(up_ask=Decimal("0.65"), down_ask=Decimal("0.35"))
    intent = s.decide(snap, holds_market=False, position=None)
    assert intent is not None
    assert intent.action == "buy"
    assert intent.side == "down"
    assert intent.notional_usdc == Decimal("5.00")
    assert intent.limit_price == Decimal("0.35")


def test_skips_when_down_ask_above_entry():
    s = _strategy()
    snap = _snap(up_ask=Decimal("0.60"), down_ask=Decimal("0.40"))
    assert s.decide(snap, holds_market=False, position=None) is None


def test_sells_when_implied_down_bid_at_exit():
    # implied down bid = 1 - up_ask = 1 - 0.45 = 0.55
    s = _strategy()
    snap = _snap(up_ask=Decimal("0.45"), down_ask=Decimal("0.55"))
    pos = _position()
    intent = s.decide(snap, holds_market=True, position=pos)
    assert intent is not None
    assert intent.action == "sell"
    assert intent.side == "down"
    assert intent.shares == pos.shares
    assert intent.limit_price == Decimal("0.55")


def test_holds_when_implied_down_bid_below_exit():
    # implied down bid = 1 - 0.50 = 0.50, below 0.55
    s = _strategy()
    snap = _snap(up_ask=Decimal("0.50"), down_ask=Decimal("0.50"))
    pos = _position()
    assert s.decide(snap, holds_market=True, position=pos) is None


def test_does_not_rebuy_while_holding():
    s = _strategy()
    snap = _snap(up_ask=Decimal("0.80"), down_ask=Decimal("0.20"))
    pos = _position()
    intent = s.decide(snap, holds_market=True, position=pos)
    # Position present; implied bid (0.20) below exit — hold.
    assert intent is None


def test_skips_when_book_empty():
    s = _strategy()
    snap = MarketSnapshot(
        market_id="m1",
        timestamp=datetime(2026, 5, 14, 12, 0, 0, tzinfo=timezone.utc),
        time_to_resolve_s=120.0,
        up_token_id="u",
        down_token_id="d",
        up_best_ask=None,
        up_best_ask_size=None,
        down_best_ask=None,
        down_best_ask_size=None,
        up_asks=[],
        down_asks=[],
    )
    assert s.decide(snap, holds_market=False, position=None) is None
