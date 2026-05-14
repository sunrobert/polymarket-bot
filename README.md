# polybot

Paper trader and backtester for Polymarket's recurring 5-minute Bitcoin
"Up or Down" markets. Multiple strategies, single skeleton.

**v1 is paper trading only.** Live execution against the CLOB is deferred to v2.

## Bots

| Bot | What it does | Needs BTC feed |
|---|---|---|
| `bot1` | Buy heavy favorites ($0.85–$0.99) in the last 1–20s. No external signal. **Likely loses money** — buys at fair prices, pays fees. | No |
| `bot2_filter` | Same trade shape as Bot 1 but only fires when BTC direction (from Coinbase) agrees with the in-band side. Safer than Bot 1. Likely still ~zero EV. | Yes |
| `bot2_signal` | Computes a fair-value `p(up wins)` from BTC move + time remaining, trades when fair value disagrees with market ask by `min_edge`. The version with plausible alpha. | Yes |

## Empirical Findings

Both `bot1` and `bot2_signal` have been paper-traded against live Polymarket data and exhibit negative expected value at their current parameterizations.

**Bot 1** demonstrates a structural rather than statistical failure: purchasing assets at prices the order book has already calibrated to near-certainty yields approximately zero pre-fee EV. Two paper sessions of 13 trades each produced realized hit rates above 90% but cumulative P&L of −$0.92 and −$0.70 respectively. The win/loss-magnitude asymmetry (gains of $0.01–$0.15, losses of $0.85–$0.99) is sufficient on its own to drive the strategy negative; the strategy is retained as a baseline for order-book-only momentum.

**Bot 2 (`bot2_signal`)** tested the hypothesis that the Polymarket book lags Coinbase BTC/USD movements within five-minute windows. Across six trades the realized hit rate was 33% (2W / 4L), with cumulative P&L of −$2.17. Three contributing factors were identified: an overconfident volatility prior (`sigma_per_sec_bps = 1.5`), temporal and instrumental misalignment between the Coinbase reference price and the Chainlink resolution oracle, and an asymmetric risk profile on tail-priced entries that requires hit rates well above 50% to break even. The hypothesis is not falsified at six trades but cannot be considered supported at the current parameter values.

Full analysis: [`docs/bot-postmortems.md`](docs/bot-postmortems.md).

## Setup

    python -m venv .venv
    source .venv/bin/activate
    pip install -e ".[dev]"

## Run paper

    python scripts/run_paper.py --bot bot1
    python scripts/run_paper.py --bot bot2_filter
    python scripts/run_paper.py --bot bot2_signal

Each bot writes its recording to `recordings/<bot>/YYYY-MM-DD.jsonl` so multiple
bots can run side-by-side without overwriting each other.

## Backtest

    python scripts/run_backtest.py recordings/bot2_signal/2026-05-14.jsonl --bot bot2_signal

A recording captured by `bot2_*` includes BTC reference prices and can be replayed
by any bot. A `bot1` recording has no BTC data, so `bot2_*` will skip every trade
when replaying it.

## Test

    pytest

## Check live markets

    python scripts/check_markets.py

Lists upcoming `btc-up-or-down-5m` events. Use this to confirm there's something
tradeable before starting a paper run.
