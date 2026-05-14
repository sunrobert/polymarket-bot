"""Paper-trade selected bot against live Polymarket data. No real orders are placed.

Usage:
    python scripts/run_paper.py --bot bot1
    python scripts/run_paper.py --bot bot2_filter
    python scripts/run_paper.py --bot bot2_signal

Each bot records to its own subdirectory under config.recorder.dir so runs are
comparable without overwriting each other.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from polybot.btc_feed import CoinbasePriceFeed
from polybot.config import load_config
from polybot.executor.paper import PaperExecutor
from polybot.feed.live import LiveFeed
from polybot.portfolio import Portfolio
from polybot.recorder import Recorder
from polybot.runner import run_loop
from polybot.strategy import BOT_NAMES, BOTS_NEEDING_BTC_FEED, make_strategy

SUMMARY_INTERVAL_S = 30.0


async def _periodic_summary(portfolio: Portfolio, bot: str):
    while True:
        await asyncio.sleep(SUMMARY_INTERVAL_S)
        print(
            f"[{bot}] trades={portfolio.day_trades} "
            f"day_pnl={portfolio.day_pnl} "
            f"total_pnl={portfolio.total_pnl} "
            f"open={len(portfolio.open_positions())} "
            f"halted={portfolio.is_halted()}",
            flush=True,
        )


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--bot",
        choices=BOT_NAMES,
        default="bot1",
        help="which strategy to run",
    )
    parser.add_argument(
        "--config", type=Path, default=Path("config.yaml"), help="config file"
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    cfg = load_config(args.config)

    btc_feed = CoinbasePriceFeed() if args.bot in BOTS_NEEDING_BTC_FEED else None
    feed = LiveFeed(cfg.feed, btc_feed=btc_feed)
    strategy = make_strategy(args.bot, cfg)
    executor = PaperExecutor()
    portfolio = Portfolio(
        max_daily_trades=cfg.risk.max_daily_trades,
        max_daily_loss_usdc=cfg.risk.max_daily_loss_usdc,
    )

    recordings_dir = Path(cfg.recorder.dir) / args.bot
    with Recorder(dir=recordings_dir) as recorder:
        print(f"[{args.bot}] writing recording to {recorder.path}", flush=True)
        summary = asyncio.create_task(_periodic_summary(portfolio, args.bot))
        try:
            await run_loop(
                feed=feed,
                strategy=strategy,
                executor=executor,
                portfolio=portfolio,
                recorder=recorder,
            )
        finally:
            summary.cancel()

    print(f"=== {args.bot} paper run done ===")
    print(f"trades:    {portfolio.day_trades}")
    print(f"day P&L:   {portfolio.day_pnl}")
    print(f"total P&L: {portfolio.total_pnl}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        print("\ninterrupted")
        sys.exit(0)
