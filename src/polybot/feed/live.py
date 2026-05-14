"""LiveFeed: discovers the active 5-min BTC market via Gamma, subscribes to its
two outcome tokens via the CLOB WebSocket, and emits MarketSnapshots whenever
the top of book changes (plus a heartbeat every `heartbeat_interval_s`).

After the market's window ends, polls Gamma every `resolution_poll_interval_s`
until it reports resolved, then emits a ResolutionEvent and moves to the next
market.

Schema/slug assumptions live in `_discover_active_market` and `_parse_market`.
If Polymarket returns a different shape than we expect, these are the methods
to adjust.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, AsyncIterator

import httpx
import websockets

from polybot.btc_feed import CoinbasePriceFeed
from polybot.config import FeedConfig
from polybot.types import BookLevel, FeedEvent, MarketSnapshot, ResolutionEvent

log = logging.getLogger(__name__)

# Only track markets ending within this horizon. Keeps concurrent WS subscriptions
# bounded to roughly current + next-in-series.
TRACK_HORIZON_S = 10 * 60
DISCOVERY_INTERVAL_S = 15


class LiveFeed:
    def __init__(
        self,
        cfg: FeedConfig,
        btc_feed: CoinbasePriceFeed | None = None,
    ) -> None:
        self._cfg = cfg
        # When btc_feed is provided, snapshots include btc_price / btc_open_price
        # so Bot 2 can act on external BTC reference. Bot 1 doesn't need it.
        self._btc_feed = btc_feed
        # Frozen open price per market_id, looked up once when the market is
        # first tracked (via Coinbase historical candle around eventStartTime).
        self._open_prices: dict[str, Decimal | None] = {}

    async def events(self) -> AsyncIterator[FeedEvent]:
        async with httpx.AsyncClient(timeout=10.0) as http:
            if self._btc_feed is not None:
                await self._btc_feed.start()
            queue: asyncio.Queue[FeedEvent] = asyncio.Queue()
            tracked: set[str] = set()

            async def market_task(market: dict[str, Any]) -> None:
                # If we have a BTC feed, capture the open price once for this market.
                if self._btc_feed is not None and market.get("start") is not None:
                    open_price = await self._btc_feed.historical(market["start"])
                    self._open_prices[market["id"]] = open_price
                    log.info(
                        "btc open price for %s @ %s = %s",
                        market.get("slug"),
                        market["start"].isoformat(),
                        open_price,
                    )
                try:
                    async for ev in self._stream_market(http, market):
                        await queue.put(ev)
                except Exception as exc:  # noqa: BLE001
                    log.warning("market task for %s ended: %s", market.get("slug"), exc)

            async def discovery_loop() -> None:
                while True:
                    try:
                        upcoming = await self._fetch_upcoming(http)
                        for market in upcoming:
                            mid = market["id"]
                            if mid in tracked:
                                continue
                            tracked.add(mid)
                            log.info(
                                "tracking %s (ends %s)",
                                market.get("slug"),
                                market.get("end"),
                            )
                            asyncio.create_task(market_task(market))
                    except Exception as exc:  # noqa: BLE001
                        log.warning("discovery failed: %s", exc)
                    await asyncio.sleep(DISCOVERY_INTERVAL_S)

            disc = asyncio.create_task(discovery_loop())
            try:
                while True:
                    ev = await queue.get()
                    yield ev
            finally:
                disc.cancel()
                if self._btc_feed is not None:
                    await self._btc_feed.stop()

    async def _fetch_upcoming(
        self, http: httpx.AsyncClient
    ) -> list[dict[str, Any]]:
        # All upcoming events in the series with endDate within TRACK_HORIZON_S.
        url = f"{self._cfg.gamma_url}/events"
        params = {
            "series_slug": self._cfg.series_slug,
            "closed": "false",
            "limit": 100,
            "order": "endDate",
            "ascending": "true",
        }
        resp = await http.get(url, params=params)
        resp.raise_for_status()
        now = datetime.now(timezone.utc)
        horizon = now + timedelta(seconds=TRACK_HORIZON_S)
        results: list[dict[str, Any]] = []
        for raw in resp.json():
            parsed = self._parse_event(raw)
            if parsed is None:
                continue
            if parsed["end"] is None or parsed["end"] <= now:
                continue
            if parsed["end"] > horizon:
                break  # list is endDate-ascending, no point looking further
            results.append(parsed)
        return results

    def _parse_event(self, raw: dict[str, Any]) -> dict[str, Any] | None:
        # 5-min markets come back as Gamma "events" with a single inner market.
        # Pull tokens/outcomes from the inner market — they're JSON-encoded strings.
        markets = raw.get("markets") or []
        if not markets:
            log.warning("event %s has no inner markets", raw.get("slug"))
            return None
        m = markets[0]

        outcomes = m.get("outcomes")
        token_ids = m.get("clobTokenIds")
        if isinstance(outcomes, str):
            try:
                outcomes = json.loads(outcomes)
            except json.JSONDecodeError:
                outcomes = []
        if isinstance(token_ids, str):
            try:
                token_ids = json.loads(token_ids)
            except json.JSONDecodeError:
                token_ids = []

        up_id = down_id = None
        if outcomes and token_ids and len(outcomes) == len(token_ids):
            token_map = {name: tid for name, tid in zip(outcomes, token_ids)}
            up_id = token_map.get("Up") or token_map.get("up")
            down_id = token_map.get("Down") or token_map.get("down")
        if not up_id or not down_id:
            log.warning("could not extract up/down token ids from event %s", raw.get("slug"))
            return None

        end_iso = m.get("endDate") or raw.get("endDate")
        end_dt = (
            datetime.fromisoformat(end_iso.replace("Z", "+00:00"))
            if end_iso
            else None
        )
        start_iso = (
            m.get("eventStartTime")
            or raw.get("startTime")
            or raw.get("eventStartTime")
        )
        start_dt = (
            datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
            if start_iso
            else None
        )
        return {
            "id": m.get("conditionId") or m.get("id") or raw.get("id"),
            "gamma_market_id": m.get("id"),  # numeric, used for /markets/<id> polling
            "outcomes": outcomes,  # ["Up","Down"] order for outcomePrices indexing
            "slug": raw.get("slug"),
            "up_token_id": str(up_id),
            "down_token_id": str(down_id),
            "end": end_dt,
            "start": start_dt,
        }

    async def _stream_market(
        self, http: httpx.AsyncClient, market: dict[str, Any]
    ) -> AsyncIterator[FeedEvent]:
        market_id = market["id"]
        end: datetime | None = market["end"]
        log.info("streaming market %s (end=%s)", market_id, end)

        # Track latest top-of-book per token.
        state: dict[str, dict[str, Any]] = {
            "up": {"price": None, "size": None, "asks": []},
            "down": {"price": None, "size": None, "asks": []},
        }

        def make_snapshot() -> MarketSnapshot:
            now = datetime.now(timezone.utc)
            ttr = (end - now).total_seconds() if end else 0.0
            btc_price = self._btc_feed.latest() if self._btc_feed else None
            btc_open = self._open_prices.get(market_id)
            return MarketSnapshot(
                market_id=market_id,
                timestamp=now,
                time_to_resolve_s=ttr,
                up_token_id=market["up_token_id"],
                down_token_id=market["down_token_id"],
                up_best_ask=state["up"]["price"],
                up_best_ask_size=state["up"]["size"],
                down_best_ask=state["down"]["price"],
                down_best_ask_size=state["down"]["size"],
                up_asks=list(state["up"]["asks"]),
                down_asks=list(state["down"]["asks"]),
                btc_price=btc_price,
                btc_open_price=btc_open,
            )

        # Seed both sides with REST book snapshots.
        for side, token_id in (
            ("up", market["up_token_id"]),
            ("down", market["down_token_id"]),
        ):
            try:
                resp = await http.get(
                    f"{self._cfg.clob_rest_url}/book",
                    params={"token_id": token_id},
                )
                resp.raise_for_status()
                _apply_book(state[side], resp.json())
            except Exception as exc:  # noqa: BLE001
                log.warning("initial book fetch failed for %s: %s", side, exc)

        # Subscribe over WebSocket.
        sub_msg = json.dumps(
            {
                "type": "market",
                "assets_ids": [market["up_token_id"], market["down_token_id"]],
            }
        )

        snapshot_queue: asyncio.Queue[MarketSnapshot] = asyncio.Queue()
        stop = asyncio.Event()

        async def ws_task():
            try:
                async with websockets.connect(self._cfg.clob_ws_url) as ws:
                    await ws.send(sub_msg)
                    async for raw_msg in ws:
                        if stop.is_set():
                            return
                        try:
                            msg = json.loads(raw_msg)
                        except json.JSONDecodeError:
                            continue
                        # CLOB may send arrays of events or single events.
                        events = msg if isinstance(msg, list) else [msg]
                        for ev in events:
                            token_id = ev.get("asset_id") or ev.get("token_id")
                            if token_id == market["up_token_id"]:
                                _apply_book(state["up"], ev)
                            elif token_id == market["down_token_id"]:
                                _apply_book(state["down"], ev)
                        await snapshot_queue.put(make_snapshot())
            except Exception as exc:  # noqa: BLE001
                log.warning("ws stream ended: %s", exc)

        async def heartbeat_task():
            while not stop.is_set():
                await asyncio.sleep(self._cfg.heartbeat_interval_s)
                await snapshot_queue.put(make_snapshot())
                if end and datetime.now(timezone.utc) > end:
                    return

        ws_handle = asyncio.create_task(ws_task())
        hb_handle = asyncio.create_task(heartbeat_task())

        try:
            # Emit an initial snapshot immediately so downstream sees current book.
            yield make_snapshot()
            while True:
                event = await snapshot_queue.get()
                yield event
                if end and datetime.now(timezone.utc) > end:
                    break
        finally:
            stop.set()
            hb_handle.cancel()
            ws_handle.cancel()

        # Poll for resolution via /markets/<numeric_id>. Resolution publishes as
        # outcomePrices ["1","0"] (Up wins) or ["0","1"] (Down wins).
        gamma_id = market.get("gamma_market_id")
        outcomes_order = market.get("outcomes") or ["Up", "Down"]
        while gamma_id is not None:
            await asyncio.sleep(self._cfg.resolution_poll_interval_s)
            try:
                resp = await http.get(
                    f"{self._cfg.gamma_url}/markets/{gamma_id}"
                )
                resp.raise_for_status()
                raw = resp.json()
                if raw.get("closed") or raw.get("resolved"):
                    winning_side = _winning_side(raw, outcomes_order)
                    if winning_side is not None:
                        yield ResolutionEvent(
                            market_id=market_id,
                            timestamp=datetime.now(timezone.utc),
                            winning_side=winning_side,
                        )
                        return
            except Exception as exc:  # noqa: BLE001
                log.warning("resolution poll failed: %s", exc)


def _apply_book(side_state: dict, msg: dict) -> None:
    """Update side_state in place from a CLOB book message.

    Accepts both REST snapshot shape ({"asks": [["0.90","100"], ...]}) and
    WebSocket diff/full shape. Tolerant of missing fields — silently no-ops.
    """
    asks = msg.get("asks") or []
    levels = []
    for entry in asks:
        if isinstance(entry, list) and len(entry) >= 2:
            price = Decimal(str(entry[0]))
            size = Decimal(str(entry[1]))
        elif isinstance(entry, dict):
            price_raw = entry.get("price")
            size_raw = entry.get("size") or entry.get("amount")
            if price_raw is None or size_raw is None:
                continue
            price = Decimal(str(price_raw))
            size = Decimal(str(size_raw))
        else:
            continue
        if size > 0:
            levels.append(BookLevel(price=price, size=size))
    if not levels and not asks:
        # No ask info in this message — leave state untouched.
        return
    levels.sort(key=lambda lvl: lvl.price)
    side_state["asks"] = levels
    if levels:
        side_state["price"] = levels[0].price
        side_state["size"] = levels[0].size
    else:
        side_state["price"] = None
        side_state["size"] = None


def _winning_side(raw: dict, outcomes_order: list[str]) -> str | None:
    # Polymarket publishes resolution via outcomePrices: ["1","0"] or ["0","1"]
    # indexed by outcomes order. Fall back to payouts / winning_outcome for safety.
    prices = raw.get("outcomePrices")
    if isinstance(prices, str):
        try:
            prices = json.loads(prices)
        except json.JSONDecodeError:
            prices = None
    if prices and len(prices) == len(outcomes_order):
        for price, name in zip(prices, outcomes_order):
            try:
                p = float(price)
            except (TypeError, ValueError):
                continue
            if p >= 0.99:  # 1.0 means this outcome resolved true
                n = name.lower()
                if n in ("up", "down"):
                    return n

    outcome = raw.get("winning_outcome") or raw.get("winningOutcome")
    if isinstance(outcome, str):
        o = outcome.lower()
        if o in ("up", "down"):
            return o

    payouts = raw.get("payouts") or raw.get("payoutNumerators")
    if payouts and len(payouts) == len(outcomes_order):
        for payout, name in zip(payouts, outcomes_order):
            try:
                p = float(payout)
            except (TypeError, ValueError):
                continue
            if p > 0:
                n = name.lower()
                if n in ("up", "down"):
                    return n
    return None
