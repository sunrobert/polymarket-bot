from decimal import Decimal
from pathlib import Path

import pytest

from polybot.feed.historical import HistoricalFeed
from polybot.types import MarketSnapshot, ResolutionEvent

FIXTURE = Path(__file__).parent / "fixtures" / "tiny_session.jsonl"


async def test_replays_snapshots_and_resolution_in_order():
    feed = HistoricalFeed(FIXTURE)
    events = [e async for e in feed.events()]
    # 2 snapshots + 1 resolution. Intents/fills in the file are ignored by the feed.
    assert len(events) == 3
    assert isinstance(events[0], MarketSnapshot)
    assert events[0].up_best_ask == Decimal("0.92")
    assert isinstance(events[1], MarketSnapshot)
    assert events[1].time_to_resolve_s == 5
    assert isinstance(events[2], ResolutionEvent)
    assert events[2].winning_side == "up"


async def test_missing_file_raises(tmp_path: Path):
    feed = HistoricalFeed(tmp_path / "nope.jsonl")
    with pytest.raises(FileNotFoundError):
        async for _ in feed.events():
            pass
