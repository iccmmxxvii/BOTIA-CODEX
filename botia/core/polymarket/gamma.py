from __future__ import annotations
import json
import re
import requests
from typing import Any


def _get(url: str, params: dict | None = None, timeout: int = 20) -> Any:
    r = requests.get(url, params=params, timeout=timeout)
    r.raise_for_status()
    return r.json()


class GammaClient:
    def __init__(self, base: str):
        self.base = base.rstrip("/")

    def get_market_by_slug(self, slug: str) -> dict:
        # GET https://gamma-api.polymarket.com/markets/slug/{slug}
        url = f"{self.base}/markets/slug/{slug}"
        return _get(url)


def to_json_str(obj: dict) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def extract_price_to_beat(market: dict) -> float | None:
    """
    Si viene explícito, úsalo; si no, parsea del texto (question/description).
    """
    for k in ("priceToBeat", "strike", "strikePrice", "threshold", "price_to_beat"):
        v = market.get(k)
        if isinstance(v, (int, float)):
            return float(v)

    blob_parts: list[str] = []
    for k in ("question", "title", "subtitle", "description", "rules", "marketDescription"):
        v = market.get(k)
        if isinstance(v, str) and v.strip():
            blob_parts.append(v)

    blob = " | ".join(blob_parts)
    m = re.search(r"(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)", blob)
    if not m:
        return None
    num = m.group(1).replace(",", "")
    try:
        return float(num)
    except Exception:
        return None
