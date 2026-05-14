"""Replays a JSONL recording as a stream of FeedEvents.

Only `snapshot` and `resolution` lines are emitted. `intent` and `fill` lines
exist for audit and are skipped here — the strategy + executor in the replay
will produce their own.
"""
from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import AsyncIterator

from polybot.types import BookLevel, FeedEvent, MarketSnapshot, ResolutionEvent


def _parse_snapshot(raw: dict) -> MarketSnapshot:
    return MarketSnapshot(
        market_id=raw["market_id"],
        timestamp=datetime.fromisoformat(raw["timestamp"]),
        time_to_resolve_s=float(raw["time_to_resolve_s"]),
        up_token_id=raw["up_token_id"],
        down_token_id=raw["down_token_id"],
        up_best_ask=Decimal(raw["up_best_ask"]) if raw.get("up_best_ask") else None,
        up_best_ask_size=Decimal(raw["up_best_ask_size"])
        if raw.get("up_best_ask_size")
        else None,
        down_best_ask=Decimal(raw["down_best_ask"])
        if raw.get("down_best_ask")
        else None,
        down_best_ask_size=Decimal(raw["down_best_ask_size"])
        if raw.get("down_best_ask_size")
        else None,
        up_asks=[
            BookLevel(price=Decimal(lvl["price"]), size=Decimal(lvl["size"]))
            for lvl in raw.get("up_asks", [])
        ],
        down_asks=[
            BookLevel(price=Decimal(lvl["price"]), size=Decimal(lvl["size"]))
            for lvl in raw.get("down_asks", [])
        ],
        btc_price=Decimal(raw["btc_price"]) if raw.get("btc_price") else None,
        btc_open_price=Decimal(raw["btc_open_price"]) if raw.get("btc_open_price") else None,
    )


def _parse_resolution(raw: dict) -> ResolutionEvent:
    return ResolutionEvent(
        market_id=raw["market_id"],
        timestamp=datetime.fromisoformat(raw["timestamp"]),
        winning_side=raw["winning_side"],
    )


class HistoricalFeed:
    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)

    async def events(self) -> AsyncIterator[FeedEvent]:
        if not self._path.exists():
            raise FileNotFoundError(self._path)
        with self._path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                raw = json.loads(line)
                t = raw.get("type")
                if t == "snapshot":
                    yield _parse_snapshot(raw)
                elif t == "resolution":
                    yield _parse_resolution(raw)
                # intent/fill lines are intentionally skipped
