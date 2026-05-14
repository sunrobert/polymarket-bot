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
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, AsyncIterator

import httpx
import websockets

from polybot.config import FeedConfig
from polybot.types import BookLevel, FeedEvent, MarketSnapshot, ResolutionEvent

log = logging.getLogger(__name__)


class LiveFeed:
    def __init__(self, cfg: FeedConfig) -> None:
        self._cfg = cfg

    async def events(self) -> AsyncIterator[FeedEvent]:
        async with httpx.AsyncClient(timeout=10.0) as http:
            while True:
                market = await self._discover_active_market(http)
                if market is None:
                    log.warning("no active market found; retrying in 10s")
                    await asyncio.sleep(10)
                    continue
                async for ev in self._stream_market(http, market):
                    yield ev

    async def _discover_active_market(
        self, http: httpx.AsyncClient
    ) -> dict[str, Any] | None:
        # Gamma API: /markets?active=true&closed=false&limit=100
        # Filter by slug substring. Slug pattern for recurring markets has historically
        # looked like: bitcoin-up-or-down-may-14-2026-12pm-et. Adjust as needed.
        url = f"{self._cfg.gamma_url}/markets"
        params = {"active": "true", "closed": "false", "limit": 100}
        resp = await http.get(url, params=params)
        resp.raise_for_status()
        for raw in resp.json():
            slug = raw.get("slug", "")
            if self._cfg.market_slug_substring in slug:
                parsed = self._parse_market(raw)
                if parsed is not None:
                    return parsed
        return None

    def _parse_market(self, raw: dict[str, Any]) -> dict[str, Any] | None:
        # Expect two outcome tokens; map them to up/down by name.
        outcomes = raw.get("outcomes", [])
        up_id = down_id = None
        if outcomes and "clobTokenIds" in raw:
            token_map = dict(zip(outcomes, raw["clobTokenIds"]))
            up_id = token_map.get("Up") or token_map.get("up")
            down_id = token_map.get("Down") or token_map.get("down")
        else:
            tokens = raw.get("tokens") or []
            for t in tokens:
                name = (t.get("outcome") or t.get("name") or "").lower()
                if name == "up":
                    up_id = t.get("token_id") or t.get("id")
                elif name == "down":
                    down_id = t.get("token_id") or t.get("id")
        if not up_id or not down_id:
            log.warning("could not extract up/down token ids from market %s", raw.get("id"))
            return None
        end_iso = raw.get("endDateIso") or raw.get("end_date_iso") or raw.get("endDate")
        end_dt = (
            datetime.fromisoformat(end_iso.replace("Z", "+00:00"))
            if end_iso
            else None
        )
        return {
            "id": raw.get("id") or raw.get("conditionId"),
            "slug": raw.get("slug"),
            "up_token_id": str(up_id),
            "down_token_id": str(down_id),
            "end": end_dt,
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

        # Poll for resolution.
        while True:
            await asyncio.sleep(self._cfg.resolution_poll_interval_s)
            try:
                resp = await http.get(
                    f"{self._cfg.gamma_url}/markets/{market_id}"
                )
                resp.raise_for_status()
                raw = resp.json()
                if raw.get("closed") or raw.get("resolved"):
                    winning_side = _winning_side(raw)
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


def _winning_side(raw: dict) -> str | None:
    # Try common shapes for resolution payloads.
    outcome = raw.get("winning_outcome") or raw.get("winningOutcome")
    if isinstance(outcome, str):
        o = outcome.lower()
        if o in ("up", "down"):
            return o
    # Payouts: [1, 0] vs [0, 1] indexed by outcome order.
    payouts = raw.get("payouts") or raw.get("payoutNumerators")
    outcomes = raw.get("outcomes")
    if payouts and outcomes and len(payouts) == len(outcomes):
        for payout, name in zip(payouts, outcomes):
            try:
                p = float(payout)
            except (TypeError, ValueError):
                continue
            if p > 0:
                n = name.lower()
                if n in ("up", "down"):
                    return n
    return None
