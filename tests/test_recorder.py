import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from polybot.recorder import Recorder
from polybot.types import (
    BookLevel,
    Fill,
    MarketSnapshot,
    ResolutionEvent,
    TradeIntent,
)


def _ts():
    return datetime(2026, 5, 14, 12, 0, 0, tzinfo=timezone.utc)


def test_records_each_event_as_one_line(tmp_path: Path):
    rec = Recorder(dir=tmp_path, now=_ts, record_snapshots=True)
    snap = MarketSnapshot(
        market_id="m1",
        timestamp=_ts(),
        time_to_resolve_s=10,
        up_token_id="u",
        down_token_id="d",
        up_best_ask=Decimal("0.90"),
        up_best_ask_size=Decimal("100"),
        down_best_ask=Decimal("0.10"),
        down_best_ask_size=Decimal("100"),
        up_asks=[BookLevel(price=Decimal("0.90"), size=Decimal("100"))],
        down_asks=[BookLevel(price=Decimal("0.10"), size=Decimal("100"))],
    )
    intent = TradeIntent(
        intent_id="i1", market_id="m1", side="up", notional_usdc=Decimal("1.00")
    )
    fill = Fill(
        intent_id="i1",
        market_id="m1",
        side="up",
        shares=Decimal("1.111"),
        avg_price=Decimal("0.90"),
        timestamp=_ts(),
    )
    res = ResolutionEvent(market_id="m1", timestamp=_ts(), winning_side="up")

    rec.record_snapshot(snap)
    rec.record_intent(intent)
    rec.record_fill(fill)
    rec.record_resolution(res)
    rec.close()

    files = list(tmp_path.glob("*.jsonl"))
    assert len(files) == 1
    lines = files[0].read_text().splitlines()
    assert len(lines) == 4
    parsed = [json.loads(line) for line in lines]
    assert parsed[0]["type"] == "snapshot"
    assert parsed[0]["up_best_ask"] == "0.90"
    assert parsed[1]["type"] == "intent"
    assert parsed[2]["type"] == "fill"
    assert parsed[3]["type"] == "resolution"
    assert parsed[3]["winning_side"] == "up"


def test_default_skips_snapshots_to_avoid_bloat(tmp_path: Path):
    rec = Recorder(dir=tmp_path, now=_ts)  # default record_snapshots=False
    snap = MarketSnapshot(
        market_id="m1",
        timestamp=_ts(),
        time_to_resolve_s=10,
        up_token_id="u",
        down_token_id="d",
        up_best_ask=Decimal("0.90"),
        up_best_ask_size=Decimal("100"),
        down_best_ask=Decimal("0.10"),
        down_best_ask_size=Decimal("100"),
        up_asks=[],
        down_asks=[],
    )
    fill = Fill(
        intent_id="i1",
        market_id="m1",
        side="up",
        shares=Decimal("1"),
        avg_price=Decimal("0.90"),
        timestamp=_ts(),
    )
    # Spam many snapshots — none should be written.
    for _ in range(100):
        rec.record_snapshot(snap)
    rec.record_fill(fill)
    rec.close()
    lines = list(tmp_path.glob("*.jsonl"))[0].read_text().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["type"] == "fill"


def test_filename_uses_session_date(tmp_path: Path):
    fixed = datetime(2026, 5, 14, 12, 0, 0, tzinfo=timezone.utc)
    rec = Recorder(dir=tmp_path, now=lambda: fixed)
    rec.record_resolution(
        ResolutionEvent(market_id="m1", timestamp=fixed, winning_side="up")
    )
    rec.close()
    files = list(tmp_path.glob("*.jsonl"))
    assert files[0].name == "2026-05-14.jsonl"
