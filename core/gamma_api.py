from __future__ import annotations

import time
from typing import Any

import requests

from core.utils import FIXED_SLUG, parse_clob_token_ids

GAMMA_BASE = "https://gamma-api.polymarket.com"


class GammaAPI:
    def __init__(self, ttl_s: int = 60) -> None:
        self.ttl_s = ttl_s
        self._cache: dict[str, tuple[float, dict[str, Any]]] = {}

    def get_market(self, slug: str = FIXED_SLUG) -> dict[str, Any]:
        key = f"market:{slug}"
        now = time.time()
        if key in self._cache and now - self._cache[key][0] <= self.ttl_s:
            return self._cache[key][1]

        endpoints = [
            f"{GAMMA_BASE}/markets?slug={slug}",
            f"{GAMMA_BASE}/markets/slug/{slug}",
            f"{GAMMA_BASE}/events/slug/{slug}",
        ]
        result: dict[str, Any] = {}
        last_err = ""
        for url in endpoints:
            try:
                resp = requests.get(url, timeout=10)
                resp.raise_for_status()
                payload = resp.json()
                if isinstance(payload, list) and payload:
                    result = payload[0]
                    break
                if isinstance(payload, dict):
                    if "markets" in payload and isinstance(payload["markets"], list) and payload["markets"]:
                        result = payload["markets"][0]
                    else:
                        result = payload
                    break
            except Exception as exc:  # network/API exceptions
                last_err = str(exc)
        if not result:
            result = {"slug": slug, "error": f"Gamma unavailable: {last_err}"}

        result["parsed_clob_token_ids"] = parse_clob_token_ids(result.get("clobTokenIds"))
        self._cache[key] = (now, result)
        return result

    @staticmethod
    def map_up_down_tokens(market: dict[str, Any]) -> dict[str, str | None]:
        outcomes = market.get("outcomes")
        outcome_prices = market.get("outcomePrices")
        token_ids = market.get("parsed_clob_token_ids") or []

        if isinstance(outcomes, str):
            try:
                import json

                outcomes = json.loads(outcomes)
            except Exception:
                outcomes = []
        if isinstance(outcome_prices, str):
            try:
                import json

                outcome_prices = json.loads(outcome_prices)
            except Exception:
                outcome_prices = []

        up_token = None
        down_token = None
        if isinstance(outcomes, list) and isinstance(token_ids, list):
            for idx, o in enumerate(outcomes):
                name = str(o).strip().lower()
                token = token_ids[idx] if idx < len(token_ids) else None
                if name in {"yes", "up"}:
                    up_token = token
                if name in {"no", "down"}:
                    down_token = token

        return {
            "up_token": up_token,
            "down_token": down_token,
            "outcomes": outcomes if isinstance(outcomes, list) else [],
            "outcome_prices": outcome_prices if isinstance(outcome_prices, list) else [],
        }
