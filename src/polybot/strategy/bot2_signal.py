"""Bot 2 (signal version).

Trades *because of* oracle disagreement, not despite it. Computes a fair-value
estimate of p(up wins) from BTC's move since market open + time remaining, and
trades whichever side has a positive edge against the Polymarket ask:

  edge_up   = p_up_wins  - market_up_ask
  edge_down = (1 - p_up_wins) - market_down_ask
  trade if max(edge_up, edge_down) > min_edge

Model: BTC price at close ~ Normal(current_btc, sigma_per_sec * sqrt(ttr)).
p(up wins) = Phi((current_btc - open_btc) / sigma_remaining).

The sigma_per_sec_bps parameter is the critical knob. BTC daily vol ~ 4% →
per-sec ~ 1.4 bps. We expose it as config; bigger values widen the model and
make it harder to find edge (more conservative).
"""
from __future__ import annotations

import math
import uuid
from decimal import Decimal

from polybot.types import MarketSnapshot, Side, TradeIntent


def _phi(z: float) -> float:
    """Standard normal CDF."""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def _estimate_p_up(
    btc_now: Decimal,
    btc_open: Decimal,
    time_left_s: float,
    sigma_per_sec_bps: Decimal,
) -> float:
    delta = float(btc_now - btc_open)
    if time_left_s <= 0:
        return 1.0 if delta > 0 else 0.0 if delta < 0 else 0.5
    sigma_per_sec = float(btc_open) * float(sigma_per_sec_bps) / 10000.0
    sd_remaining = sigma_per_sec * math.sqrt(time_left_s)
    if sd_remaining == 0:
        return 1.0 if delta > 0 else 0.0 if delta < 0 else 0.5
    return _phi(delta / sd_remaining)


class Bot2SignalStrategy:
    def __init__(
        self,
        time_window_s: tuple[float, float],
        trade_size_usdc: Decimal,
        min_edge: Decimal,
        sigma_per_sec_bps: Decimal,
        price_band: tuple[Decimal, Decimal] | None = None,
    ) -> None:
        self.time_window_s = time_window_s
        self.trade_size_usdc = trade_size_usdc
        self.min_edge = min_edge
        self.sigma_per_sec_bps = sigma_per_sec_bps
        # Optional safety: only trade when ask is within this band. Default [0.50, 0.99].
        self.price_band = price_band or (Decimal("0.50"), Decimal("0.99"))

    def decide(
        self, snapshot: MarketSnapshot, holds_market: bool
    ) -> TradeIntent | None:
        if holds_market:
            return None

        lo_t, hi_t = self.time_window_s
        if not (lo_t <= snapshot.time_to_resolve_s <= hi_t):
            return None

        if snapshot.btc_price is None or snapshot.btc_open_price is None:
            return None
        if snapshot.up_best_ask is None or snapshot.down_best_ask is None:
            return None

        p_up = Decimal(
            str(
                _estimate_p_up(
                    snapshot.btc_price,
                    snapshot.btc_open_price,
                    snapshot.time_to_resolve_s,
                    self.sigma_per_sec_bps,
                )
            )
        )
        p_down = Decimal("1") - p_up

        edge_up = p_up - snapshot.up_best_ask
        edge_down = p_down - snapshot.down_best_ask

        lo_p, hi_p = self.price_band
        candidates: list[tuple[Decimal, Side, Decimal]] = []
        if edge_up >= self.min_edge and lo_p <= snapshot.up_best_ask <= hi_p:
            candidates.append((edge_up, "up", snapshot.up_best_ask))
        if edge_down >= self.min_edge and lo_p <= snapshot.down_best_ask <= hi_p:
            candidates.append((edge_down, "down", snapshot.down_best_ask))

        if not candidates:
            return None

        # Best edge wins.
        candidates.sort(key=lambda c: c[0], reverse=True)
        _, side, _ = candidates[0]
        return TradeIntent(
            intent_id=str(uuid.uuid4()),
            market_id=snapshot.market_id,
            side=side,
            notional_usdc=self.trade_size_usdc,
        )
