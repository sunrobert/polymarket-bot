"""Config loader. YAML on disk → pydantic models in memory."""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, model_validator


class StrategyConfig(BaseModel):
    price_band: tuple[Decimal, Decimal]
    time_window_s: tuple[float, float]
    trade_size_usdc: Decimal

    @model_validator(mode="after")
    def _ordered_band(self) -> "StrategyConfig":
        lo, hi = self.price_band
        if lo >= hi:
            raise ValueError(f"price_band must be increasing, got {self.price_band}")
        w_lo, w_hi = self.time_window_s
        if w_lo >= w_hi:
            raise ValueError(f"time_window_s must be increasing, got {self.time_window_s}")
        if self.trade_size_usdc <= 0:
            raise ValueError("trade_size_usdc must be > 0")
        return self


class Bot2FilterConfig(BaseModel):
    price_band: tuple[Decimal, Decimal]
    time_window_s: tuple[float, float]
    trade_size_usdc: Decimal


class Bot2SignalConfig(BaseModel):
    time_window_s: tuple[float, float]
    trade_size_usdc: Decimal
    min_edge: Decimal
    sigma_per_sec_bps: Decimal
    price_band: tuple[Decimal, Decimal]


class Bot3DipBuyerConfig(BaseModel):
    entry_price: Decimal
    exit_price: Decimal
    trade_size_usdc: Decimal

    @model_validator(mode="after")
    def _ordered(self) -> "Bot3DipBuyerConfig":
        if self.entry_price <= 0 or self.entry_price >= self.exit_price:
            raise ValueError(
                f"need 0 < entry_price < exit_price, got "
                f"{self.entry_price}/{self.exit_price}"
            )
        if self.trade_size_usdc <= 0:
            raise ValueError("trade_size_usdc must be > 0")
        return self


class Bot4RallyFaderConfig(BaseModel):
    entry_price: Decimal
    exit_price: Decimal
    trade_size_usdc: Decimal

    @model_validator(mode="after")
    def _ordered(self) -> "Bot4RallyFaderConfig":
        if self.entry_price <= 0 or self.entry_price >= self.exit_price:
            raise ValueError(
                f"need 0 < entry_price < exit_price, got "
                f"{self.entry_price}/{self.exit_price}"
            )
        if self.trade_size_usdc <= 0:
            raise ValueError("trade_size_usdc must be > 0")
        return self


class Bot5BothSidesConfig(BaseModel):
    entry_price: Decimal
    exit_price: Decimal
    trade_size_usdc: Decimal

    @model_validator(mode="after")
    def _ordered(self) -> "Bot5BothSidesConfig":
        if self.entry_price <= 0 or self.entry_price >= self.exit_price:
            raise ValueError(
                f"need 0 < entry_price < exit_price, got "
                f"{self.entry_price}/{self.exit_price}"
            )
        if self.trade_size_usdc <= 0:
            raise ValueError("trade_size_usdc must be > 0")
        return self


class Bot6SmartDipBuyerConfig(BaseModel):
    entry_price: Decimal
    exit_price: Decimal
    trade_size_usdc: Decimal
    max_dip_pct: Decimal
    growth_window: int

    @model_validator(mode="after")
    def _ordered(self) -> "Bot6SmartDipBuyerConfig":
        if self.entry_price <= 0 or self.entry_price >= self.exit_price:
            raise ValueError(
                f"need 0 < entry_price < exit_price, got "
                f"{self.entry_price}/{self.exit_price}"
            )
        if self.trade_size_usdc <= 0:
            raise ValueError("trade_size_usdc must be > 0")
        if not (Decimal("0") < self.max_dip_pct < Decimal("1")):
            raise ValueError(f"max_dip_pct must be in (0, 1), got {self.max_dip_pct}")
        if self.growth_window < 2:
            raise ValueError(f"growth_window must be >= 2, got {self.growth_window}")
        return self


class Bot7SpeculationConfig(BaseModel):
    entry_price: Decimal
    exit_price: Decimal
    trade_size_usdc: Decimal
    entry_cutoff_s: float
    force_exit_s: float

    @model_validator(mode="after")
    def _ordered(self) -> "Bot7SpeculationConfig":
        if self.entry_price <= 0 or self.entry_price >= self.exit_price:
            raise ValueError(
                f"need 0 < entry_price < exit_price, got "
                f"{self.entry_price}/{self.exit_price}"
            )
        if self.trade_size_usdc <= 0:
            raise ValueError("trade_size_usdc must be > 0")
        if self.entry_cutoff_s <= 0 or self.force_exit_s <= 0:
            raise ValueError("entry_cutoff_s and force_exit_s must be > 0")
        return self


class RiskConfig(BaseModel):
    max_daily_trades: int = Field(gt=0)
    max_daily_loss_usdc: Decimal = Field(gt=0)


class RecorderConfig(BaseModel):
    dir: str


class FeedConfig(BaseModel):
    gamma_url: str
    clob_ws_url: str
    clob_rest_url: str
    series_slug: str
    heartbeat_interval_s: float = Field(gt=0)
    resolution_poll_interval_s: float = Field(gt=0)


class Config(BaseModel):
    strategy: StrategyConfig
    risk: RiskConfig
    recorder: RecorderConfig
    feed: FeedConfig
    bot2_filter: Bot2FilterConfig | None = None
    bot2_signal: Bot2SignalConfig | None = None
    bot3_dipbuyer: Bot3DipBuyerConfig | None = None
    bot4_rallyfader: Bot4RallyFaderConfig | None = None
    bot5_bothsides: Bot5BothSidesConfig | None = None
    bot6_smartdipbuyer: Bot6SmartDipBuyerConfig | None = None
    bot7_speculation: Bot7SpeculationConfig | None = None


def load_config(path: Path | str) -> Config:
    raw = yaml.safe_load(Path(path).read_text())
    return Config.model_validate(raw)
