"""Replay a recorded session through Bot 1 and print summary P&L."""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from polybot.config import load_config
from polybot.executor.paper import PaperExecutor
from polybot.feed.historical import HistoricalFeed
from polybot.portfolio import Portfolio
from polybot.recorder import Recorder
from polybot.runner import run_loop
from polybot.strategy.bot1 import Bot1Strategy


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("recording", type=Path, help="JSONL recording to replay")
    parser.add_argument(
        "--config", type=Path, default=Path("config.yaml"), help="config file"
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    cfg = load_config(args.config)

    feed = HistoricalFeed(args.recording)
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
        await run_loop(
            feed=feed,
            strategy=strategy,
            executor=executor,
            portfolio=portfolio,
            recorder=recorder,
        )

    print("=== Backtest done ===")
    print(f"trades:    {portfolio.day_trades}")
    print(f"day P&L:   {portfolio.day_pnl}")
    print(f"total P&L: {portfolio.total_pnl}")
    print(f"open:      {len(portfolio.open_positions())}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
