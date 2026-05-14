from datetime import datetime, timezone
from decimal import Decimal

from polybot.strategy.bot2_signal import Bot2SignalStrategy, _estimate_p_up
from polybot.types import BookLevel, MarketSnapshot


def _snap(
    *,
    ttr: float,
    up_ask: Decimal,
    down_ask: Decimal,
    btc_now: Decimal,
    btc_open: Decimal,
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
        btc_price=btc_now,
        btc_open_price=btc_open,
    )


def _strategy(min_edge="0.02") -> Bot2SignalStrategy:
    return Bot2SignalStrategy(
        time_window_s=(5.0, 20.0),
        trade_size_usdc=Decimal("1.00"),
        min_edge=Decimal(min_edge),
        sigma_per_sec_bps=Decimal("1.5"),
        price_band=(Decimal("0.05"), Decimal("0.99")),
    )


def test_p_up_50_when_flat():
    p = _estimate_p_up(
        btc_now=Decimal("90000"),
        btc_open=Decimal("90000"),
        time_left_s=10.0,
        sigma_per_sec_bps=Decimal("1.5"),
    )
    assert abs(p - 0.5) < 1e-9


def test_p_up_high_when_btc_clearly_up():
    # BTC up $200 from $90k with 5s left and ~1.5 bps/sec vol → very confident Up
    p = _estimate_p_up(
        btc_now=Decimal("90200"),
        btc_open=Decimal("90000"),
        time_left_s=5.0,
        sigma_per_sec_bps=Decimal("1.5"),
    )
    assert p > 0.99


def test_p_up_low_when_btc_clearly_down():
    p = _estimate_p_up(
        btc_now=Decimal("89800"),
        btc_open=Decimal("90000"),
        time_left_s=5.0,
        sigma_per_sec_bps=Decimal("1.5"),
    )
    assert p < 0.01


def test_buys_up_when_market_underprices_clear_uptrend():
    # BTC obviously up, but market ask on Up is only $0.85 → big edge buying Up.
    s = _strategy()
    snap = _snap(
        ttr=5,
        up_ask=Decimal("0.85"),
        down_ask=Decimal("0.15"),
        btc_now=Decimal("90200"),
        btc_open=Decimal("90000"),
    )
    intent = s.decide(snap, holds_market=False)
    assert intent is not None
    assert intent.side == "up"


def test_buys_down_when_market_underprices_clear_downtrend():
    s = _strategy()
    snap = _snap(
        ttr=5,
        up_ask=Decimal("0.85"),
        down_ask=Decimal("0.15"),
        btc_now=Decimal("89800"),
        btc_open=Decimal("90000"),
    )
    intent = s.decide(snap, holds_market=False)
    assert intent is not None
    assert intent.side == "down"


def test_skips_when_market_correctly_prices_direction():
    # BTC up clearly, market ask on Up is $0.99 → no edge to take.
    s = _strategy()
    snap = _snap(
        ttr=5,
        up_ask=Decimal("0.99"),
        down_ask=Decimal("0.01"),
        btc_now=Decimal("90200"),
        btc_open=Decimal("90000"),
    )
    assert s.decide(snap, holds_market=False) is None


def test_skips_when_flat_and_market_is_balanced():
    s = _strategy()
    snap = _snap(
        ttr=10,
        up_ask=Decimal("0.51"),
        down_ask=Decimal("0.51"),
        btc_now=Decimal("90000"),
        btc_open=Decimal("90000"),
    )
    assert s.decide(snap, holds_market=False) is None


def test_outside_window_skips():
    s = _strategy()
    snap = _snap(
        ttr=3,
        up_ask=Decimal("0.85"),
        down_ask=Decimal("0.15"),
        btc_now=Decimal("90200"),
        btc_open=Decimal("90000"),
    )
    assert s.decide(snap, holds_market=False) is None


def test_already_holding_skips():
    s = _strategy()
    snap = _snap(
        ttr=5,
        up_ask=Decimal("0.85"),
        down_ask=Decimal("0.15"),
        btc_now=Decimal("90200"),
        btc_open=Decimal("90000"),
    )
    assert s.decide(snap, holds_market=True) is None


def test_missing_btc_data_skips():
    s = _strategy()
    snap = MarketSnapshot(
        market_id="m1",
        timestamp=datetime(2026, 5, 14, 12, 0, 0, tzinfo=timezone.utc),
        time_to_resolve_s=5,
        up_token_id="u",
        down_token_id="d",
        up_best_ask=Decimal("0.85"),
        up_best_ask_size=Decimal("100"),
        down_best_ask=Decimal("0.15"),
        down_best_ask_size=Decimal("100"),
        up_asks=[],
        down_asks=[],
        btc_price=None,
        btc_open_price=None,
    )
    assert s.decide(snap, holds_market=False) is None
