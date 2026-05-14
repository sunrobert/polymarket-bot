"""Coinbase BTC/USD price feed.

Provides:
  - latest() — the most recent BTC/USD tick, updated from Coinbase WebSocket.
  - historical(ts) — BTC/USD price at a past timestamp, used for market open prices.

Why Coinbase over Chainlink: Chainlink aggregates from Coinbase (and others) before
publishing, so reading Coinbase directly gives us the same signal with less latency.
Free, public, no wallet needed.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from decimal import Decimal

import httpx
import websockets

log = logging.getLogger(__name__)

WS_URL = "wss://ws-feed.exchange.coinbase.com"
REST_URL = "https://api.exchange.coinbase.com"
PRODUCT = "BTC-USD"


class CoinbasePriceFeed:
    def __init__(self) -> None:
        self._latest: Decimal | None = None
        self._latest_ts: datetime | None = None
        self._task: asyncio.Task | None = None
        self._http: httpx.AsyncClient | None = None

    async def start(self) -> None:
        self._http = httpx.AsyncClient(timeout=10.0)
        self._task = asyncio.create_task(self._run_ws())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
        if self._http:
            await self._http.aclose()

    def latest(self) -> Decimal | None:
        return self._latest

    async def historical(self, ts: datetime) -> Decimal | None:
        """Return BTC/USD around `ts` using Coinbase minute candles.

        Returns the open of the minute candle that contains `ts`, which is a
        reasonable proxy for "BTC price at exactly ts" given Chainlink-cadence
        oracle resolutions.
        """
        if self._http is None:
            log.warning("historical() called before start()")
            return None
        # Coinbase wants ISO timestamps; we fetch a 5-minute window centered on ts.
        start = ts.replace(second=0, microsecond=0)
        end = start.replace(minute=start.minute)
        try:
            resp = await self._http.get(
                f"{REST_URL}/products/{PRODUCT}/candles",
                params={
                    "start": start.isoformat(),
                    "end": end.isoformat(),
                    "granularity": 60,
                },
            )
            resp.raise_for_status()
            candles = resp.json()
        except Exception as exc:  # noqa: BLE001
            log.warning("historical fetch failed for %s: %s", ts.isoformat(), exc)
            return None

        if not candles:
            return None
        # Each candle: [time, low, high, open, close, volume]. Use open of the candle
        # whose start timestamp matches our target minute (if present).
        target_unix = int(start.replace(tzinfo=timezone.utc).timestamp())
        for candle in candles:
            if int(candle[0]) == target_unix:
                return Decimal(str(candle[3]))  # open
        # Fall back to the most recent candle's close as a rough estimate.
        latest = max(candles, key=lambda c: c[0])
        return Decimal(str(latest[4]))

    async def _run_ws(self) -> None:
        sub_msg = json.dumps(
            {
                "type": "subscribe",
                "channels": [{"name": "ticker", "product_ids": [PRODUCT]}],
            }
        )
        while True:
            try:
                async with websockets.connect(WS_URL) as ws:
                    await ws.send(sub_msg)
                    async for raw in ws:
                        try:
                            msg = json.loads(raw)
                        except json.JSONDecodeError:
                            continue
                        if msg.get("type") == "ticker" and msg.get("product_id") == PRODUCT:
                            price = msg.get("price")
                            if price is not None:
                                try:
                                    self._latest = Decimal(str(price))
                                    self._latest_ts = datetime.now(timezone.utc)
                                except Exception:  # noqa: BLE001
                                    pass
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                log.warning("coinbase ws disconnected (%s); reconnecting in 5s", exc)
                await asyncio.sleep(5)
