from datetime import datetime, timezone
from decimal import Decimal

from polybot.portfolio import Portfolio
from polybot.types import Fill, ResolutionEvent


def _ts():
    return datetime(2026, 5, 14, 12, 0, 0, tzinfo=timezone.utc)


def _fill(market_id: str = "m1", side: str = "up") -> Fill:
    # $1 of notional at $0.90 → 1.1111... shares
    shares = Decimal("1.00") / Decimal("0.90")
    return Fill(
        intent_id=f"i-{market_id}",
        market_id=market_id,
        side=side,  # type: ignore[arg-type]
        shares=shares,
        avg_price=Decimal("0.90"),
        timestamp=_ts(),
    )


def test_holds_market_after_fill():
    p = Portfolio(max_daily_trades=10, max_daily_loss_usdc=Decimal("10"))
    assert not p.holds_market("m1")
    p.apply_fill(_fill())
    assert p.holds_market("m1")


def test_winning_resolution_pays_one_dollar_per_share():
    p = Portfolio(max_daily_trades=10, max_daily_loss_usdc=Decimal("10"))
    p.apply_fill(_fill(side="up"))
    p.apply_resolution(ResolutionEvent(market_id="m1", timestamp=_ts(), winning_side="up"))
    # shares ≈ 1.1111, cost $1 → P&L ≈ $0.1111
    expected = (Decimal("1.00") / Decimal("0.90")) - (Decimal("1.00") / Decimal("0.90")) * Decimal("0.90")
    assert p.day_pnl == expected
    assert p.total_pnl == expected


def test_losing_resolution_loses_cost():
    p = Portfolio(max_daily_trades=10, max_daily_loss_usdc=Decimal("10"))
    p.apply_fill(_fill(side="up"))
    p.apply_resolution(
        ResolutionEvent(market_id="m1", timestamp=_ts(), winning_side="down")
    )
    # cost = shares * avg_price = (1/0.90) * 0.90 ≈ 1.00 (with Decimal precision)
    expected_cost = (Decimal("1.00") / Decimal("0.90")) * Decimal("0.90")
    assert p.day_pnl == -expected_cost


def test_kill_switch_max_daily_trades():
    p = Portfolio(max_daily_trades=2, max_daily_loss_usdc=Decimal("10"))
    p.apply_fill(_fill(market_id="m1"))
    p.apply_fill(_fill(market_id="m2"))
    assert p.day_trades == 2
    assert p.is_halted() is True


def test_kill_switch_max_daily_loss():
    p = Portfolio(max_daily_trades=100, max_daily_loss_usdc=Decimal("1.50"))
    p.apply_fill(_fill(market_id="m1"))
    p.apply_resolution(
        ResolutionEvent(market_id="m1", timestamp=_ts(), winning_side="down")
    )
    p.apply_fill(_fill(market_id="m2"))
    p.apply_resolution(
        ResolutionEvent(market_id="m2", timestamp=_ts(), winning_side="down")
    )
    # day_pnl ≈ -$2.00, exceeds -$1.50
    assert p.is_halted() is True


def test_not_halted_initially():
    p = Portfolio(max_daily_trades=10, max_daily_loss_usdc=Decimal("10"))
    assert p.is_halted() is False


def test_resolution_for_unknown_market_is_noop():
    p = Portfolio(max_daily_trades=10, max_daily_loss_usdc=Decimal("10"))
    p.apply_resolution(
        ResolutionEvent(market_id="ghost", timestamp=_ts(), winning_side="up")
    )
    assert p.day_pnl == Decimal("0")


def test_sell_fill_books_pnl_and_closes():
    p = Portfolio(max_daily_trades=10, max_daily_loss_usdc=Decimal("10"))
    # Bought 10 Up shares at $0.30 → cost $3.00
    p.apply_fill(
        Fill(
            intent_id="b1",
            market_id="m1",
            side="up",
            shares=Decimal("10"),
            avg_price=Decimal("0.30"),
            timestamp=_ts(),
            action="buy",
        )
    )
    assert p.holds_market("m1")
    # Sell all 10 shares at $0.55 → proceeds $5.50, P&L = +$2.50
    p.apply_fill(
        Fill(
            intent_id="s1",
            market_id="m1",
            side="up",
            shares=Decimal("10"),
            avg_price=Decimal("0.55"),
            timestamp=_ts(),
            action="sell",
        )
    )
    assert p.day_pnl == Decimal("2.50")
    assert p.total_pnl == Decimal("2.50")
    assert not p.holds_market("m1")
    assert p.get_position("m1") is None


def test_get_position_returns_active_position():
    p = Portfolio(max_daily_trades=10, max_daily_loss_usdc=Decimal("10"))
    assert p.get_position("m1") is None
    p.apply_fill(_fill())
    pos = p.get_position("m1")
    assert pos is not None
    assert pos.market_id == "m1"
    assert pos.side == "up"
