"""Strategy factory. Add new bots here and they become selectable via --bot."""
from __future__ import annotations

from polybot.config import Config
from polybot.strategy.bot1 import Bot1Strategy
from polybot.strategy.bot2_filter import Bot2FilterStrategy
from polybot.strategy.bot2_signal import Bot2SignalStrategy
from polybot.strategy.bot3_dipbuyer import Bot3DipBuyerStrategy
from polybot.strategy.bot4_rallyfader import Bot4RallyFaderStrategy
from polybot.strategy.bot5_bothsides import Bot5BothSidesStrategy
from polybot.strategy.bot6_smartdipbuyer import Bot6SmartDipBuyerStrategy


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
    if name == "bot3_dipbuyer":
        b3 = cfg.bot3_dipbuyer
        if b3 is None:
            raise ValueError("bot3_dipbuyer selected but config.bot3_dipbuyer is missing")
        return Bot3DipBuyerStrategy(
            entry_price=b3.entry_price,
            exit_price=b3.exit_price,
            trade_size_usdc=b3.trade_size_usdc,
        )
    if name == "bot4_rallyfader":
        b4 = cfg.bot4_rallyfader
        if b4 is None:
            raise ValueError("bot4_rallyfader selected but config.bot4_rallyfader is missing")
        return Bot4RallyFaderStrategy(
            entry_price=b4.entry_price,
            exit_price=b4.exit_price,
            trade_size_usdc=b4.trade_size_usdc,
        )
    if name == "bot5_bothsides":
        b5 = cfg.bot5_bothsides
        if b5 is None:
            raise ValueError("bot5_bothsides selected but config.bot5_bothsides is missing")
        return Bot5BothSidesStrategy(
            entry_price=b5.entry_price,
            exit_price=b5.exit_price,
            trade_size_usdc=b5.trade_size_usdc,
        )
    if name == "bot6_smartdipbuyer":
        b6 = cfg.bot6_smartdipbuyer
        if b6 is None:
            raise ValueError("bot6_smartdipbuyer selected but config.bot6_smartdipbuyer is missing")
        return Bot6SmartDipBuyerStrategy(
            entry_price=b6.entry_price,
            exit_price=b6.exit_price,
            trade_size_usdc=b6.trade_size_usdc,
            max_dip_pct=b6.max_dip_pct,
            growth_window=b6.growth_window,
        )
    raise ValueError(f"unknown strategy: {name}")


BOT_NAMES = (
    "bot1",
    "bot2_filter",
    "bot2_signal",
    "bot3_dipbuyer",
    "bot4_rallyfader",
    "bot5_bothsides",
    "bot6_smartdipbuyer",
)
BOTS_NEEDING_BTC_FEED = ("bot2_filter", "bot2_signal")
