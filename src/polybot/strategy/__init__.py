"""Strategy factory. Add new bots here and they become selectable via --bot."""
from __future__ import annotations

from polybot.config import Config
from polybot.strategy.bot1 import Bot1Strategy
from polybot.strategy.bot2_filter import Bot2FilterStrategy
from polybot.strategy.bot2_signal import Bot2SignalStrategy


def make_strategy(name: str, cfg: Config):
    if name == "bot1":
        return Bot1Strategy(
            price_band=cfg.strategy.price_band,
            time_window_s=cfg.strategy.time_window_s,
            trade_size_usdc=cfg.strategy.trade_size_usdc,
        )
    if name == "bot2_filter":
        b2 = cfg.bot2_filter
        if b2 is None:
            raise ValueError("bot2_filter selected but config.bot2_filter is missing")
        return Bot2FilterStrategy(
            price_band=b2.price_band,
            time_window_s=b2.time_window_s,
            trade_size_usdc=b2.trade_size_usdc,
        )
    if name == "bot2_signal":
        b2 = cfg.bot2_signal
        if b2 is None:
            raise ValueError("bot2_signal selected but config.bot2_signal is missing")
        return Bot2SignalStrategy(
            time_window_s=b2.time_window_s,
            trade_size_usdc=b2.trade_size_usdc,
            min_edge=b2.min_edge,
            sigma_per_sec_bps=b2.sigma_per_sec_bps,
            price_band=b2.price_band,
        )
    raise ValueError(f"unknown strategy: {name}")


BOT_NAMES = ("bot1", "bot2_filter", "bot2_signal")
BOTS_NEEDING_BTC_FEED = ("bot2_filter", "bot2_signal")
