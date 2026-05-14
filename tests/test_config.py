from decimal import Decimal
from pathlib import Path

import pytest

from polybot.config import Config, load_config


YAML = """
strategy:
  price_band: [0.85, 0.99]
  time_window_s: [1, 20]
  trade_size_usdc: 1.00
bot2_filter:
  price_band: [0.85, 0.95]
  time_window_s: [5, 20]
  trade_size_usdc: 1.00
bot2_signal:
  time_window_s: [5, 20]
  trade_size_usdc: 1.00
  min_edge: 0.02
  sigma_per_sec_bps: 1.5
  price_band: [0.05, 0.99]
bot3_dipbuyer:
  entry_price: 0.35
  exit_price: 0.55
  trade_size_usdc: 5.00
bot4_rallyfader:
  entry_price: 0.35
  exit_price: 0.55
  trade_size_usdc: 5.00
bot5_bothsides:
  entry_price: 0.35
  exit_price: 0.55
  trade_size_usdc: 5.00
bot6_smartdipbuyer:
  entry_price: 0.35
  exit_price: 0.55
  trade_size_usdc: 5.00
  max_dip_pct: 0.50
  growth_window: 5
risk:
  max_daily_trades: 50
  max_daily_loss_usdc: 10.00
recorder:
  dir: recordings
feed:
  gamma_url: https://gamma-api.polymarket.com
  clob_ws_url: wss://ws-subscriptions-clob.polymarket.com/ws/market
  clob_rest_url: https://clob.polymarket.com
  series_slug: btc-up-or-down-5m
  heartbeat_interval_s: 1.0
  resolution_poll_interval_s: 5.0
"""


def test_load_config_parses_decimal(tmp_path: Path):
    p = tmp_path / "c.yaml"
    p.write_text(YAML)
    cfg = load_config(p)
    assert isinstance(cfg, Config)
    assert cfg.strategy.price_band == (Decimal("0.85"), Decimal("0.99"))
    assert cfg.strategy.time_window_s == (1.0, 20.0)
    assert cfg.strategy.trade_size_usdc == Decimal("1.00")
    assert cfg.risk.max_daily_trades == 50
    assert cfg.risk.max_daily_loss_usdc == Decimal("10.00")
    assert cfg.recorder.dir == "recordings"
    assert cfg.feed.series_slug == "btc-up-or-down-5m"
    assert cfg.bot3_dipbuyer is not None
    assert cfg.bot3_dipbuyer.entry_price == Decimal("0.35")
    assert cfg.bot3_dipbuyer.exit_price == Decimal("0.55")
    assert cfg.bot3_dipbuyer.trade_size_usdc == Decimal("5.00")


def test_load_config_rejects_bad_band(tmp_path: Path):
    p = tmp_path / "c.yaml"
    p.write_text(YAML.replace("[0.85, 0.99]", "[0.99, 0.85]"))
    with pytest.raises(ValueError):
        load_config(p)
