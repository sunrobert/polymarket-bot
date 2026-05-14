"""Executor interface. Paper in v1; live in v2."""
from __future__ import annotations

from typing import Protocol

from polybot.types import Fill, TradeIntent


class Executor(Protocol):
    async def submit(self, intent: TradeIntent) -> Fill | None: ...
