from datetime import datetime, timezone
from decimal import Decimal

from polybot.strategy.bot2_filter import Bot2FilterStrategy
from polybot.types import BookLevel, MarketSnapshot


def _snap(
    *,
    ttr: float,
    up_ask: Decimal | None,
    down_ask: Decimal | None,
    btc_now: Decimal | None,
    btc_open: Decimal | None,
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
        btc_price=btc_now,
        btc_open_price=btc_open,
    )


def _strategy() -> Bot2FilterStrategy:
    return Bot2FilterStrategy(
        price_band=(Decimal("0.85"), Decimal("0.95")),
        time_window_s=(5.0, 20.0),
        trade_size_usdc=Decimal("1.00"),
    )


def test_up_favorite_btc_up_trades():
    s = _strategy()
    snap = _snap(
        ttr=10,
        up_ask=Decimal("0.92"),
        down_ask=Decimal("0.10"),
        btc_now=Decimal("90100"),
        btc_open=Decimal("90000"),
    )
    intent = s.decide(snap, holds_market=False)
    assert intent is not None
    assert intent.side == "up"


def test_up_favorite_btc_down_skips():
    s = _strategy()
    snap = _snap(
        ttr=10,
        up_ask=Decimal("0.92"),
        down_ask=Decimal("0.10"),
        btc_now=Decimal("89900"),  # BTC fell, but market favors Up — mispriced
        btc_open=Decimal("90000"),
    )
    assert s.decide(snap, holds_market=False) is None


def test_down_favorite_btc_down_trades():
    s = _strategy()
    snap = _snap(
        ttr=10,
        up_ask=Decimal("0.10"),
        down_ask=Decimal("0.92"),
        btc_now=Decimal("89900"),
        btc_open=Decimal("90000"),
    )
    intent = s.decide(snap, holds_market=False)
    assert intent is not None
    assert intent.side == "down"


def test_down_favorite_btc_up_skips():
    s = _strategy()
    snap = _snap(
        ttr=10,
        up_ask=Decimal("0.10"),
        down_ask=Decimal("0.92"),
        btc_now=Decimal("90100"),
        btc_open=Decimal("90000"),
    )
    assert s.decide(snap, holds_market=False) is None


def test_missing_btc_data_skips():
    s = _strategy()
    snap = _snap(
        ttr=10,
        up_ask=Decimal("0.92"),
        down_ask=Decimal("0.10"),
        btc_now=None,
        btc_open=Decimal("90000"),
    )
    assert s.decide(snap, holds_market=False) is None


def test_above_band_skips():
    s = _strategy()
    snap = _snap(
        ttr=10,
        up_ask=Decimal("0.97"),  # outside [0.85, 0.95]
        down_ask=Decimal("0.10"),
        btc_now=Decimal("90100"),
        btc_open=Decimal("90000"),
    )
    assert s.decide(snap, holds_market=False) is None


def test_outside_window_skips():
    s = _strategy()
    snap = _snap(
        ttr=3,  # outside [5, 20]
        up_ask=Decimal("0.92"),
        down_ask=Decimal("0.10"),
        btc_now=Decimal("90100"),
        btc_open=Decimal("90000"),
    )
    assert s.decide(snap, holds_market=False) is None


def test_already_holding_skips():
    s = _strategy()
    snap = _snap(
        ttr=10,
        up_ask=Decimal("0.92"),
        down_ask=Decimal("0.10"),
        btc_now=Decimal("90100"),
        btc_open=Decimal("90000"),
    )
    assert s.decide(snap, holds_market=True) is None


def test_btc_unchanged_treats_as_up():
    # btc_now == btc_open. We treat "no move" as up-direction (>= compare).
    # The filter intent is "don't trade against direction"; flat is not against.
    s = _strategy()
    snap = _snap(
        ttr=10,
        up_ask=Decimal("0.92"),
        down_ask=Decimal("0.10"),
        btc_now=Decimal("90000"),
        btc_open=Decimal("90000"),
    )
    intent = s.decide(snap, holds_market=False)
    assert intent is not None
    assert intent.side == "up"
