from datetime import datetime, timezone
from decimal import Decimal

from polybot.strategy.bot1 import Bot1Strategy
from polybot.types import BookLevel, MarketSnapshot


def _snap(
    *,
    ttr: float,
    up_ask: Decimal | None,
    down_ask: Decimal | None,
    market_id: str = "m1",
) -> MarketSnapshot:
    return MarketSnapshot(
        market_id=market_id,
        timestamp=datetime(2026, 5, 14, 12, 0, 0, tzinfo=timezone.utc),
        time_to_resolve_s=ttr,
        up_token_id="u",
        down_token_id="d",
        up_best_ask=up_ask,
        up_best_ask_size=Decimal("100") if up_ask else None,
        down_best_ask=down_ask,
        down_best_ask_size=Decimal("100") if down_ask else None,
        up_asks=[BookLevel(price=up_ask, size=Decimal("100"))] if up_ask else [],
        down_asks=[BookLevel(price=down_ask, size=Decimal("100"))] if down_ask else [],
    )


def _strategy() -> Bot1Strategy:
    return Bot1Strategy(
        price_band=(Decimal("0.85"), Decimal("0.99")),
        time_window_s=(1.0, 20.0),
        trade_size_usdc=Decimal("1.00"),
    )


def test_in_band_in_window_up_emits_intent():
    s = _strategy()
    snap = _snap(ttr=10, up_ask=Decimal("0.92"), down_ask=Decimal("0.10"))
    intent = s.decide(snap, holds_market=False)
    assert intent is not None
    assert intent.side == "up"
    assert intent.market_id == "m1"
    assert intent.notional_usdc == Decimal("1.00")


def test_in_band_in_window_down_emits_intent():
    s = _strategy()
    snap = _snap(ttr=5, up_ask=Decimal("0.10"), down_ask=Decimal("0.92"))
    intent = s.decide(snap, holds_market=False)
    assert intent is not None
    assert intent.side == "down"


def test_outside_window_too_early_no_trade():
    s = _strategy()
    snap = _snap(ttr=30, up_ask=Decimal("0.92"), down_ask=Decimal("0.10"))
    assert s.decide(snap, holds_market=False) is None


def test_outside_window_too_late_no_trade():
    s = _strategy()
    snap = _snap(ttr=0.5, up_ask=Decimal("0.92"), down_ask=Decimal("0.10"))
    assert s.decide(snap, holds_market=False) is None


def test_in_window_below_band_no_trade():
    s = _strategy()
    snap = _snap(ttr=10, up_ask=Decimal("0.80"), down_ask=Decimal("0.22"))
    assert s.decide(snap, holds_market=False) is None


def test_in_window_above_band_no_trade():
    s = _strategy()
    snap = _snap(ttr=10, up_ask=Decimal("0.999"), down_ask=Decimal("0.005"))
    assert s.decide(snap, holds_market=False) is None


def test_already_holding_no_trade():
    s = _strategy()
    snap = _snap(ttr=10, up_ask=Decimal("0.92"), down_ask=Decimal("0.10"))
    assert s.decide(snap, holds_market=True) is None


def test_both_sides_in_band_ambiguous_no_trade():
    s = _strategy()
    snap = _snap(ttr=10, up_ask=Decimal("0.90"), down_ask=Decimal("0.88"))
    assert s.decide(snap, holds_market=False) is None


def test_missing_ask_treated_as_not_in_band():
    s = _strategy()
    snap = _snap(ttr=10, up_ask=None, down_ask=Decimal("0.92"))
    intent = s.decide(snap, holds_market=False)
    assert intent is not None
    assert intent.side == "down"


def test_intent_id_is_stable_per_market_decision():
    s = _strategy()
    snap = _snap(ttr=10, up_ask=Decimal("0.92"), down_ask=Decimal("0.10"))
    i1 = s.decide(snap, holds_market=False)
    i2 = s.decide(snap, holds_market=False)
    assert i1 is not None and i2 is not None
    assert i1.intent_id != i2.intent_id  # each call produces a fresh id
