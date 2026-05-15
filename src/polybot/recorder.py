"""JSON Lines recorder. Every snapshot, intent, fill, and resolution gets one line.

Output files match `recordings/YYYY-MM-DD.jsonl` where the date is when the
recorder was constructed (one file per session).
"""
from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import IO, Callable

from polybot.types import Fill, MarketSnapshot, ResolutionEvent, TradeIntent


def _default_now() -> datetime:
    return datetime.now(timezone.utc)


def _encode(obj):
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    if is_dataclass(obj):
        return asdict(obj)
    raise TypeError(f"Unserializable: {type(obj)}")


class Recorder:
    def __init__(
        self,
        dir: Path | str,
        now: Callable[[], datetime] = _default_now,
        record_snapshots: bool = False,
    ) -> None:
        self._dir = Path(dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        date_str = now().date().isoformat()
        self._path = self._dir / f"{date_str}.jsonl"
        self._fh: IO[str] = self._path.open("a", encoding="utf-8")
        self._record_snapshots = record_snapshots

    @property
    def path(self) -> Path:
        return self._path

    def record_snapshot(self, snap: MarketSnapshot) -> None:
        # Snapshots dominate file size — several per second per market with the
        # full ask ladder. Off by default; turn on only when you need replay.
        if not self._record_snapshots:
            return
        self._write("snapshot", asdict(snap))

    def record_intent(self, intent: TradeIntent) -> None:
        self._write("intent", asdict(intent))

    def record_fill(self, fill: Fill) -> None:
        self._write("fill", asdict(fill))

    def record_resolution(self, event: ResolutionEvent) -> None:
        self._write("resolution", asdict(event))

    def _write(self, event_type: str, payload: dict) -> None:
        payload = {"type": event_type, **payload}
        self._fh.write(json.dumps(payload, default=_encode) + "\n")
        self._fh.flush()

    def close(self) -> None:
        if not self._fh.closed:
            self._fh.close()

    def __enter__(self) -> "Recorder":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()
