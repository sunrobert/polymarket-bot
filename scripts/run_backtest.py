"""Replay a recorded session through the selected bot and print summary P&L.

Usage:
    python scripts/run_backtest.py recording.jsonl --bot bot1
    python scripts/run_backtest.py recording.jsonl --bot bot2_filter
    python scripts/run_backtest.py recording.jsonl --bot bot2_signal

Replay output is written to recordings/<bot>/replay-<date>.jsonl so it doesn't
collide with live recordings.
"""
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
from polybot.strategy import BOT_NAMES, make_strategy


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("recording", type=Path, help="JSONL recording to replay")
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

    feed = HistoricalFeed(args.recording)
    strategy = make_strategy(args.bot, cfg)
    executor = PaperExecutor()
    portfolio = Portfolio(
        max_daily_trades=cfg.risk.max_daily_trades,
        max_daily_loss_usdc=cfg.risk.max_daily_loss_usdc,
    )
    recordings_dir = Path(cfg.recorder.dir) / args.bot / "replays"
    with Recorder(dir=recordings_dir) as recorder:
        await run_loop(
            feed=feed,
            strategy=strategy,
            executor=executor,
            portfolio=portfolio,
            recorder=recorder,
        )

    print(f"=== Backtest done [{args.bot}] ===")
    print(f"trades:    {portfolio.day_trades}")
    print(f"day P&L:   {portfolio.day_pnl}")
    print(f"total P&L: {portfolio.total_pnl}")
    print(f"open:      {len(portfolio.open_positions())}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
