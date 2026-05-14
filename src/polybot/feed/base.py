"""DataFeed interface. Yields MarketSnapshot and ResolutionEvent in order."""
from __future__ import annotations

from typing import AsyncIterator, Protocol

from polybot.types import FeedEvent


class DataFeed(Protocol):
    def events(self) -> AsyncIterator[FeedEvent]: ...
