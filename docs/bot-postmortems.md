# Strategy Postmortems: Bot 1 and Bot 2 on `btc-up-or-down-5m`

This document records empirical findings from paper-trading two strategies against Polymarket's recurring five-minute Bitcoin Up/Down series. All results are from simulated execution against live order books; no on-chain trades were placed. Both strategies are retained in the codebase for reproducibility and as comparative baselines.

---

## Bot 1 — Late-Window Favorite Buyer

### Strategy

Bot 1 buys whichever outcome (Up or Down) is trading in the price band `[$0.85, $0.99]` during the final `[1s, 20s]` before market resolution, with a fixed notional of $1 per trade. No external signal is used; the strategy relies entirely on the order book.

### Empirical Results

The strategy was paper-traded across two independent sessions on the recurring 5-minute BTC markets:

| Session | Trades | Approx. Win Rate | Net P&L |
|---------|--------|------------------|---------|
| 2026-05-13 | 13 | ~92% | −$0.92 |
| 2026-05-14 | 13 | ~92% | −$0.70 |

Both sessions terminated with negative cumulative P&L despite hit rates exceeding 90%.

### Analysis

The negative outcome is structural rather than statistical. The strategy purchases assets at prices the market has already deemed close to certain. Under the efficient-market hypothesis as applied to a liquid CLOB, the equilibrium expectation of a $0.95 contract paying $1.00 conditional on resolution is approximately $0.95, yielding zero expected value before fees. Polymarket's fee schedule (`fee = shares × feeRate × p × (1 − p)`) is minimized at the tails, but remains a strictly negative drag on EV.

The win-rate / loss-magnitude asymmetry is the dominant failure mode. Wins return $0.01–$0.15; losses return −$0.85 to −$0.99. Across 26 observed trades, two large losses fully erased the accumulated micro-wins.

### Implications

- Bayesian adjustment of the price band does not improve EV: every band on a calibrated market produces approximately zero pre-fee EV.
- Position sizing does not improve EV: it merely scales the negative drift.
- Stop-loss logic is inapplicable: prediction markets resolve to $0 or $1 with no intermediate exit signal.

The strategy is retained as a baseline demonstrating that order-book-only momentum on calibrated short-duration markets does not produce edge.

---

## Bot 2 — BTC Oracle Disagreement Signal

### Strategy

Bot 2 (`bot2_signal` variant) constructs a parametric estimate of `p(Up wins)` from the observed BTC/USD price path:

```
p_up = Φ( (BTC_now − BTC_open) / (σ · √t_remaining) )
```

where `Φ` is the standard normal CDF, `σ` is parameterized by `sigma_per_sec_bps` (default 1.5 bps), and `BTC_open` is the BTC price at the market's event-start instant, sourced from Coinbase's 1-minute candle endpoint. The bot enters a position on the side for which `|fair_p − market_ask| ≥ min_edge` (default 0.02).

### Empirical Results

Across approximately two hours of live paper trading on 2026-05-14:

| # | Side | Entry Price | Outcome | Trade P&L |
|---|------|-------------|---------|-----------|
| 1 | down | 0.56 | down won | +$0.79 |
| 2 | down | 0.24 | up won | −$1.00 |
| 3 | down | 0.58 | up won | −$1.00 |
| 4 | down | 0.31 | up won | −$1.00 |
| 5 | up | 0.49 | up won | +$1.04 |
| 6 | up | 0.17 | down won | −$1.00 |

**Net P&L: −$2.17 across 6 trades; realized hit rate 2/6 ≈ 33%.**

### Analysis

The strategy fires when the model disagrees with the market price by more than `min_edge`. Across the observed sample, the market was correctly calibrated in 4 of 6 disagreements. Several factors contribute:

1. **Overconfident volatility prior.** `sigma_per_sec_bps = 1.5` corresponds to an implied annualized BTC volatility well below realized intraday levels for short windows, causing the model to assign extreme probabilities to outcomes the market correctly prices as uncertain. Empirically observed BTC paths exhibit substantial intra-window mean reversion that the Brownian-drift assumption underweights.

2. **Reference-price misalignment.** The Coinbase 1-minute candle open used for `BTC_open` does not coincide temporally or instrumentally with the Chainlink-derived resolution oracle. The resulting noise is small in absolute terms but material relative to the typical 5-minute BTC range.

3. **Asymmetric risk profile on tail entries.** When the model fires at a market ask of $0.17–$0.31, a single resolution against the model erases the proceeds of three to five successful tail entries. With realized hit rate below 50%, this configuration is structurally negative-EV.

4. **No demonstrated information advantage over the order book.** The hypothesis underlying Bot 2 was that the Polymarket book lags BTC oracle movements within the 5-minute window. The observed disagreements consistently resolved in the market's favor, providing no evidence for this hypothesis at the tested parameter values.

### Implications

- The current parameterization is not deployable.
- A retest requires raising `sigma_per_sec_bps` to ≈3.0 to widen the prior and reduce false-positive signal generation.
- The hypothesis remains testable but requires a sample of at least 20 trades before drawing inferences; six trades is insufficient to reject either edge or no-edge at conventional significance levels.

### Variant: `bot2_filter`

The `bot2_filter` variant uses the BTC oracle only to gate Bot 1's trade on directional agreement. It was not paper-traded standalone in the recorded sessions. By construction it inherits Bot 1's zero-edge structure with reduced trade frequency; no improvement in EV is expected from the gating mechanism alone.

---

## Summary

Neither Bot 1 nor Bot 2 in its current configuration demonstrates positive expected value on the `btc-up-or-down-5m` series under paper trading. Bot 1's failure is structural and not parameter-tunable. Bot 2's failure is partly parameter-driven and partly hypothesis-driven, and warrants further testing at wider volatility priors before the underlying BTC-oracle-disagreement hypothesis can be considered falsified.

Subsequent strategies (e.g., `bot3_dipbuyer`) are designed to test orthogonal hypotheses about microstructure inefficiency rather than directional oracle disagreement.
