# polybot

Polymarket Bot 1 — paper trader and backtester for the recurring 5-minute Bitcoin
"Up or Down" market. Buys heavily-favored contracts ($0.85–$0.99) in the final
1–20 seconds before resolution, $1 per trade.

**v1 is paper trading only.** Live execution against the CLOB is deferred to v2.

## Setup

    python -m venv .venv
    source .venv/bin/activate
    pip install -e ".[dev]"

## Run

    python scripts/run_paper.py            # paper trade against live data
    python scripts/run_backtest.py FILE    # replay a recorded session

## Test

    pytest
