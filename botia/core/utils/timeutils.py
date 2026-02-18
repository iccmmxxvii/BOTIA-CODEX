from __future__ import annotations
from datetime import datetime, timezone


def now_ms() -> int:
    return int(datetime.now(tz=timezone.utc).timestamp() * 1000)


def iso_to_ms(iso: str) -> int | None:
    try:
        s = iso.strip().replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1000)
    except Exception:
        return None


def nearest_tick(ts_ms: int, ticks: list[tuple[int, float]]) -> tuple[int, float] | None:
    if not ticks:
        return None
    return min(ticks, key=lambda x: abs(x[0] - ts_ms))
