from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, List

FIXED_SLUG = "btc-updown-5m-1771209600"
FIXED_SYMBOL = "btc/usd"
RTDS_WS_URL = "wss://ws-live-data.polymarket.com"


@dataclass
class RuntimeStats:
    """Runtime counters safe to read/write from main thread."""

    reconnect_count: int = 0
    last_msg_time: float | None = None
    last_err: str = "INIT"
    started_at: float = field(default_factory=time.time)
    connected: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "reconnect_count": self.reconnect_count,
            "last_msg_time": self.last_msg_time,
            "last_err": self.last_err,
            "connected": self.connected,
            "uptime_s": max(0.0, time.time() - self.started_at),
        }


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_end_ts_from_slug(slug: str = FIXED_SLUG) -> int:
    parts = slug.split("-")
    if not parts:
        raise ValueError("Invalid slug")
    try:
        return int(parts[-1])
    except ValueError as exc:
        raise ValueError(f"Cannot parse end_ts from slug: {slug}") from exc


def parse_clob_token_ids(raw: Any) -> List[str]:
    """Robust parser for clobTokenIds from Gamma responses.

    Supports list[str], JSON string list, or fallback single token string.
    """
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(x) for x in raw if x is not None]
    if isinstance(raw, str):
        cleaned = raw.strip()
        if not cleaned:
            return []
        if cleaned.startswith("["):
            try:
                parsed = json.loads(cleaned)
                if isinstance(parsed, list):
                    return [str(x) for x in parsed if x is not None]
            except json.JSONDecodeError:
                return []
        return [cleaned]
    return [str(raw)]


def safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def first_on_or_after(points: Iterable[tuple[int, float]], ts_s: int) -> tuple[int, float] | None:
    target_ms = ts_s * 1000
    before = None
    for ts_ms, price in points:
        if ts_ms >= target_ms:
            return ts_ms, price
        before = (ts_ms, price)
    return before
