from datetime import datetime, timezone
from decimal import Decimal

from polybot.strategy.bot7_speculation import Bot7SpeculationStrategy
from polybot.types import BookLevel, MarketSnapshot, Position


def _snap(
    *, ttr: float, up_ask: Decimal = Decimal("0.35"), down_ask: Decimal = Decimal("0.65")
) -> MarketSnapshot:
    return MarketSnapshot(
        market_id="m1",
        timestamp=datetime(2026, 5, 14, 12, 0, 0, tzinfo=timezone.utc),
        time_to_resolve_s=ttr,
        up_token_id="u",
        down_token_id="d",
        up_best_ask=up_ask,
        up_best_ask_size=Decimal("100"),
        down_best_ask=down_ask,
        down_best_ask_size=Decimal("100"),
        up_asks=[BookLevel(price=up_ask, size=Decimal("100"))],
        down_asks=[BookLevel(price=down_ask, size=Decimal("100"))],
    )


def _strategy(**kwargs) -> Bot7SpeculationStrategy:
    defaults = dict(
        entry_price=Decimal("0.35"),
        exit_price=Decimal("0.55"),
        trade_size_usdc=Decimal("5.00"),
        entry_cutoff_s=150.0,
        force_exit_s=150.0,
    )
    defaults.update(kwargs)
    return Bot7SpeculationStrategy(**defaults)


def _position(shares: Decimal = Decimal("14.29")) -> Position:
    return Position(
        market_id="m1",
        side="up",
        shares=shares,
        cost_usdc=Decimal("5.00"),
        opened_at=datetime(2026, 5, 14, 12, 0, 0, tzinfo=timezone.utc),
    )


def test_buys_during_early_window():
    s = _strategy()
    snap = _snap(ttr=200, up_ask=Decimal("0.35"))
    intent = s.decide(snap, holds_market=False, position=None)
    assert intent is not None
    assert intent.action == "buy"
    assert intent.limit_price == Decimal("0.35")


def test_skips_entry_past_cutoff():
    s = _strategy()
    # 2:00 remaining, past 2:30 entry cutoff — must not enter even on a perfect dip.
    snap = _snap(ttr=120, up_ask=Decimal("0.30"))
    assert s.decide(snap, holds_market=False, position=None) is None


def test_skips_entry_at_cutoff_exactly():
    s = _strategy()
    snap = _snap(ttr=150, up_ask=Decimal("0.30"))
    assert s.decide(snap, holds_market=False, position=None) is None


def test_normal_profit_exit_within_window():
    s = _strategy()
    # 4:00 remaining, implied bid = 1 - 0.45 = 0.55 → take profit at limit.
    snap = _snap(ttr=240, up_ask=Decimal("0.55"), down_ask=Decimal("0.45"))
    pos = _position()
    intent = s.decide(snap, holds_market=True, position=pos)
    assert intent is not None
    assert intent.action == "sell"
    assert intent.limit_price == Decimal("0.55")


def test_force_exit_at_time_stop_uses_market_sell():
    s = _strategy()
    # 2:00 remaining, no bounce — force exit at whatever price.
    snap = _snap(ttr=120, up_ask=Decimal("0.30"), down_ask=Decimal("0.70"))
    pos = _position()
    intent = s.decide(snap, holds_market=True, position=pos)
    assert intent is not None
    assert intent.action == "sell"
    # No limit_price = market sell, walk the book and take whatever.
    assert intent.limit_price is None
    assert intent.shares == pos.shares


def test_force_exit_takes_priority_over_profit_exit():
    # If we're past the time stop, exit at market even if profit threshold is met.
    # (Equivalent outcome in this case but tests the precedence ordering.)
    s = _strategy()
    snap = _snap(ttr=100, up_ask=Decimal("0.60"), down_ask=Decimal("0.40"))
    pos = _position()
    intent = s.decide(snap, holds_market=True, position=pos)
    assert intent is not None
    assert intent.action == "sell"
    assert intent.limit_price is None  # market, not limit


def test_no_action_when_holding_without_exit_trigger():
    s = _strategy()
    # Mid-window, implied bid 0.50 (below exit 0.55), no force exit.
    snap = _snap(ttr=240, up_ask=Decimal("0.50"), down_ask=Decimal("0.50"))
    pos = _position()
    assert s.decide(snap, holds_market=True, position=pos) is None
