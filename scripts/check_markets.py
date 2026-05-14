"""Quick diagnostic: list upcoming btc-updown-5m events from Gamma so you can
tell at a glance whether the bot has anything to trade right now.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
from pathlib import Path

import httpx

from polybot.config import load_config


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config", type=Path, default=Path("config.yaml"), help="config file"
    )
    args = parser.parse_args()
    cfg = load_config(args.config)

    async with httpx.AsyncClient(timeout=10.0) as http:
        resp = await http.get(
            f"{cfg.feed.gamma_url}/events",
            params={
                "series_slug": cfg.feed.series_slug,
                "closed": "false",
                "limit": 100,
                "order": "endDate",
                "ascending": "true",
            },
        )
        resp.raise_for_status()
        events = resp.json()

    now = datetime.now(timezone.utc)
    hits = []
    for ev in events:
        end_iso = ev.get("endDate")
        end = (
            datetime.fromisoformat(end_iso.replace("Z", "+00:00"))
            if end_iso
            else None
        )
        mins = (end - now).total_seconds() / 60 if end else None
        hits.append((mins, ev.get("slug"), end_iso, ev.get("closed"), ev.get("active")))

    if not hits:
        print(f"No events for series '{cfg.feed.series_slug}'.")
        return 1

    future = [h for h in hits if h[0] is not None and h[0] > 0]
    if not future:
        print("Found events but all have resolved. Most recent ones:")
        for m, s, e, c, a in hits[-5:]:
            print(f"  resolved {abs(m):.1f}min ago  closed={c}  {s}")
        return 1

    print(f"Now (UTC): {now.isoformat()}")
    print(f"{len(future)} upcoming events in series '{cfg.feed.series_slug}':")
    for m, s, e, c, a in future[:10]:
        flag = "  <-- tradeable now" if 0 < m < 5 else ""
        print(f"  +{m:6.2f}min  closed={c}  active={a}  {s}{flag}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(asyncio.run(main()))
