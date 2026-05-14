from decimal import Decimal
from pathlib import Path

from polybot.executor.paper import PaperExecutor
from polybot.feed.historical import HistoricalFeed
from polybot.portfolio import Portfolio
from polybot.recorder import Recorder
from polybot.runner import run_loop
from polybot.strategy.bot1 import Bot1Strategy

FIXTURE = Path(__file__).parent / "fixtures" / "tiny_session.jsonl"


async def test_replay_produces_expected_pnl(tmp_path: Path):
    feed = HistoricalFeed(FIXTURE)
    strategy = Bot1Strategy(
        price_band=(Decimal("0.85"), Decimal("0.99")),
        time_window_s=(1.0, 20.0),
        trade_size_usdc=Decimal("1.00"),
    )
    executor = PaperExecutor()
    portfolio = Portfolio(max_daily_trades=10, max_daily_loss_usdc=Decimal("10"))
    recorder = Recorder(dir=tmp_path)

    await run_loop(
        feed=feed,
        strategy=strategy,
        executor=executor,
        portfolio=portfolio,
        recorder=recorder,
    )

    # Fixture: snapshot1 at $0.92 (ttr=15) → buys "up". Cost = 1/0.92 * 0.92.
    # Resolution: up wins. Payout = shares = 1/0.92.
    shares = Decimal("1") / Decimal("0.92")
    cost = shares * Decimal("0.92")
    expected_pnl = shares - cost
    assert portfolio.day_pnl == expected_pnl
    assert portfolio.day_trades == 1
    assert portfolio.holds_market("m1") is False  # resolved

    recorder.close()
    # Recorder wrote at least the resolution and the fill it observed.
    out = list(tmp_path.glob("*.jsonl"))
    assert len(out) == 1
    assert out[0].stat().st_size > 0


async def test_kill_switch_blocks_trades(tmp_path: Path):
    feed = HistoricalFeed(FIXTURE)
    strategy = Bot1Strategy(
        price_band=(Decimal("0.85"), Decimal("0.99")),
        time_window_s=(1.0, 20.0),
        trade_size_usdc=Decimal("1.00"),
    )
    executor = PaperExecutor()
    portfolio = Portfolio(max_daily_trades=10, max_daily_loss_usdc=Decimal("10"))
    portfolio.day_trades = 10  # already at the cap
    recorder = Recorder(dir=tmp_path)

    await run_loop(
        feed=feed,
        strategy=strategy,
        executor=executor,
        portfolio=portfolio,
        recorder=recorder,
    )

    assert portfolio.day_trades == 10  # unchanged: no trades executed
    recorder.close()
