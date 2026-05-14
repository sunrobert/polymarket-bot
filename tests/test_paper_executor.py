from datetime import datetime, timezone
from decimal import Decimal

from polybot.executor.paper import PaperExecutor
from polybot.types import BookLevel, MarketSnapshot, TradeIntent


def _ts():
    return datetime(2026, 5, 14, 12, 0, 0, tzinfo=timezone.utc)


def _snap_with_up_asks(levels: list[tuple[str, str]]) -> MarketSnapshot:
    asks = [BookLevel(price=Decimal(p), size=Decimal(s)) for p, s in levels]
    return MarketSnapshot(
        market_id="m1",
        timestamp=_ts(),
        time_to_resolve_s=5,
        up_token_id="u",
        down_token_id="d",
        up_best_ask=asks[0].price if asks else None,
        up_best_ask_size=asks[0].size if asks else None,
        down_best_ask=Decimal("0.10"),
        down_best_ask_size=Decimal("1000"),
        up_asks=asks,
        down_asks=[BookLevel(price=Decimal("0.10"), size=Decimal("1000"))],
    )


async def test_fills_at_top_when_size_dominates():
    ex = PaperExecutor()
    snap = _snap_with_up_asks([("0.90", "1000")])
    ex.on_snapshot(snap)
    intent = TradeIntent(
        intent_id="i1", market_id="m1", side="up", notional_usdc=Decimal("1.00")
    )
    fill = await ex.submit(intent)
    assert fill is not None
    assert fill.avg_price == Decimal("0.90")
    # $1 / $0.90 ≈ 1.1111 shares
    assert fill.shares == Decimal("1") / Decimal("0.90")


async def test_walks_book_when_top_level_too_thin():
    ex = PaperExecutor()
    # Top level: 0.5 shares @ $0.90 → $0.45 of notional.
    # Next level:  1.0 shares @ $0.95 → fills remaining $0.55 = 0.5789... shares.
    snap = _snap_with_up_asks([("0.90", "0.5"), ("0.95", "1.0")])
    ex.on_snapshot(snap)
    intent = TradeIntent(
        intent_id="i2", market_id="m1", side="up", notional_usdc=Decimal("1.00")
    )
    fill = await ex.submit(intent)
    assert fill is not None
    # avg_price = $1 / shares; shares = 0.5 + 0.55/0.95
    expected_shares = Decimal("0.5") + (Decimal("0.55") / Decimal("0.95"))
    assert fill.shares == expected_shares
    assert fill.avg_price == Decimal("1.00") / expected_shares


async def test_no_snapshot_returns_none():
    ex = PaperExecutor()
    intent = TradeIntent(
        intent_id="i3", market_id="m1", side="up", notional_usdc=Decimal("1.00")
    )
    assert await ex.submit(intent) is None


async def test_empty_book_returns_none():
    ex = PaperExecutor()
    ex.on_snapshot(_snap_with_up_asks([]))
    intent = TradeIntent(
        intent_id="i4", market_id="m1", side="up", notional_usdc=Decimal("1.00")
    )
    assert await ex.submit(intent) is None


async def test_book_too_thin_to_fill_returns_none():
    ex = PaperExecutor()
    # Only $0.40 of liquidity total; $1 intent can't fill.
    snap = _snap_with_up_asks([("0.80", "0.5")])
    ex.on_snapshot(snap)
    intent = TradeIntent(
        intent_id="i5", market_id="m1", side="up", notional_usdc=Decimal("1.00")
    )
    assert await ex.submit(intent) is None
