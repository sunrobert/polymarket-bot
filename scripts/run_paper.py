"""Paper-trade Bot 1 against live Polymarket data. No real orders are placed.

v1 prints a running summary every N seconds and writes a JSONL recording for
later replay. Ctrl-C exits cleanly.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from polybot.config import load_config
from polybot.executor.paper import PaperExecutor
from polybot.feed.live import LiveFeed
from polybot.portfolio import Portfolio
from polybot.recorder import Recorder
from polybot.runner import run_loop
from polybot.strategy.bot1 import Bot1Strategy

SUMMARY_INTERVAL_S = 30.0


async def _periodic_summary(portfolio: Portfolio):
    while True:
        await asyncio.sleep(SUMMARY_INTERVAL_S)
        print(
            f"[summary] trades={portfolio.day_trades} "
            f"day_pnl={portfolio.day_pnl} "
            f"total_pnl={portfolio.total_pnl} "
            f"open={len(portfolio.open_positions())} "
            f"halted={portfolio.is_halted()}",
            flush=True,
        )


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config", type=Path, default=Path("config.yaml"), help="config file"
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    cfg = load_config(args.config)

    feed = LiveFeed(cfg.feed)
    strategy = Bot1Strategy(
        price_band=cfg.strategy.price_band,
        time_window_s=cfg.strategy.time_window_s,
        trade_size_usdc=cfg.strategy.trade_size_usdc,
    )
    executor = PaperExecutor()
    portfolio = Portfolio(
        max_daily_trades=cfg.risk.max_daily_trades,
        max_daily_loss_usdc=cfg.risk.max_daily_loss_usdc,
    )

    with Recorder(dir=cfg.recorder.dir) as recorder:
        summary = asyncio.create_task(_periodic_summary(portfolio))
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

    print("=== Paper run done ===")
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
