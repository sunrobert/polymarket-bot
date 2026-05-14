from datetime import datetime, timezone
from decimal import Decimal

from polybot.strategy.bot6_smartdipbuyer import Bot6SmartDipBuyerStrategy
from polybot.types import BookLevel, MarketSnapshot, Position


def _snap(*, up_ask: Decimal, down_ask: Decimal = Decimal("0.65")) -> MarketSnapshot:
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


def _strategy(**kwargs) -> Bot6SmartDipBuyerStrategy:
    defaults = dict(
        entry_price=Decimal("0.35"),
        exit_price=Decimal("0.55"),
        trade_size_usdc=Decimal("5.00"),
        max_dip_pct=Decimal("0.50"),
        growth_window=5,
    )
    defaults.update(kwargs)
    return Bot6SmartDipBuyerStrategy(**defaults)


def _feed(s: Bot6SmartDipBuyerStrategy, prices: list[str]) -> None:
    """Feed a sequence of Up asks through decide() to build up history."""
    for p in prices:
        s.decide(_snap(up_ask=Decimal(p)), holds_market=False, position=None)


def test_skips_when_history_too_short():
    s = _strategy()
    # Only 4 snapshots seen total, growth_window=5 → no entry even on a perfect setup.
    _feed(s, ["0.25", "0.30", "0.33"])
    intent = s.decide(_snap(up_ask=Decimal("0.35")), holds_market=False, position=None)
    assert intent is None


def test_buys_when_dip_and_clear_growth():
    s = _strategy()
    # History climbs 0.20 -> 0.35: monotonic, net positive, ends at entry price.
    _feed(s, ["0.20", "0.25", "0.30", "0.33"])
    intent = s.decide(_snap(up_ask=Decimal("0.35")), holds_market=False, position=None)
    assert intent is not None
    assert intent.action == "buy"
    assert intent.side == "up"
    assert intent.limit_price == Decimal("0.35")


def test_skips_when_history_not_monotonic():
    s = _strategy()
    # Bounces around: not monotonic non-decreasing.
    _feed(s, ["0.20", "0.30", "0.25", "0.33"])
    intent = s.decide(_snap(up_ask=Decimal("0.35")), holds_market=False, position=None)
    assert intent is None


def test_skips_when_history_flat():
    s = _strategy()
    # Flat — non-decreasing but no net growth.
    _feed(s, ["0.35", "0.35", "0.35", "0.35"])
    intent = s.decide(_snap(up_ask=Decimal("0.35")), holds_market=False, position=None)
    assert intent is None


def test_skips_when_dipped_more_than_max_pct():
    s = _strategy(max_dip_pct=Decimal("0.50"))
    # Session high 0.80 → floor = 0.40. Current 0.35 < 0.40 → skip even though
    # the recent window looks great (the 0.80 falls out of the window).
    _feed(s, ["0.80", "0.20", "0.22", "0.25", "0.30", "0.33"])
    intent = s.decide(_snap(up_ask=Decimal("0.35")), holds_market=False, position=None)
    assert intent is None


def test_buys_when_dip_within_max_pct():
    s = _strategy(max_dip_pct=Decimal("0.50"))
    # Session high 0.60 → floor = 0.30. Current 0.35 >= 0.30 → allow.
    # Push extra prices so 0.60 falls out of the growth window, leaving the
    # monotonic 0.20 → 0.33 tail visible to the momentum filter.
    _feed(s, ["0.60", "0.20", "0.22", "0.25", "0.30", "0.33"])
    intent = s.decide(_snap(up_ask=Decimal("0.35")), holds_market=False, position=None)
    assert intent is not None
    assert intent.action == "buy"


def test_sells_on_exit_like_bot3():
    s = _strategy()
    # implied up bid = 1 - 0.45 = 0.55 → exit
    snap = _snap(up_ask=Decimal("0.55"), down_ask=Decimal("0.45"))
    pos = Position(
        market_id="m1",
        side="up",
        shares=Decimal("14.29"),
        cost_usdc=Decimal("5.00"),
        opened_at=datetime(2026, 5, 14, 12, 0, 0, tzinfo=timezone.utc),
    )
    intent = s.decide(snap, holds_market=True, position=pos)
    assert intent is not None
    assert intent.action == "sell"
    assert intent.shares == pos.shares
    assert intent.limit_price == Decimal("0.55")


def test_history_updates_even_while_holding():
    # Important: session high should track even during a held position so the
    # next entry after exit uses fresh data.
    s = _strategy()
    pos = Position(
        market_id="m1",
        side="up",
        shares=Decimal("14.29"),
        cost_usdc=Decimal("5.00"),
        opened_at=datetime(2026, 5, 14, 12, 0, 0, tzinfo=timezone.utc),
    )
    s.decide(_snap(up_ask=Decimal("0.70")), holds_market=True, position=pos)
    assert s._session_high["m1"] == Decimal("0.70")
