from __future__ import annotations

from typing import Any

import requests

CLOB_BASE = "https://clob.polymarket.com"


class CLOBPricing:
    """Read-only pricing helper for token midpoint extraction."""

    def get_token_mid(self, token_id: str) -> dict[str, Any]:
        if not token_id:
            return {"mid": None, "bid": None, "ask": None, "error": "missing token id"}
        endpoints = [
            f"{CLOB_BASE}/midpoint?token_id={token_id}",
            f"{CLOB_BASE}/book?token_id={token_id}",
            f"{CLOB_BASE}/price?token_id={token_id}",
        ]
        last_err = ""
        for url in endpoints:
            try:
                resp = requests.get(url, timeout=10)
                resp.raise_for_status()
                payload = resp.json()
                parsed = self._parse_price_payload(payload)
                if parsed["mid"] is not None:
                    return parsed
            except Exception as exc:
                last_err = str(exc)
        return {"mid": None, "bid": None, "ask": None, "error": last_err or "no price"}

    @staticmethod
    def _to_float(v: Any) -> float | None:
        try:
            return float(v)
        except Exception:
            return None

    def _parse_price_payload(self, payload: Any) -> dict[str, Any]:
        if isinstance(payload, dict):
            mid = self._to_float(payload.get("mid") or payload.get("midpoint") or payload.get("price"))
            bid = self._to_float(payload.get("best_bid") or payload.get("bid"))
            ask = self._to_float(payload.get("best_ask") or payload.get("ask"))
            if mid is None and bid is not None and ask is not None:
                mid = (bid + ask) / 2
            if mid is None:
                bids = payload.get("bids") or []
                asks = payload.get("asks") or []
                if bids and asks:
                    bid = self._to_float(bids[0][0] if isinstance(bids[0], list) else bids[0].get("price"))
                    ask = self._to_float(asks[0][0] if isinstance(asks[0], list) else asks[0].get("price"))
                    if bid is not None and ask is not None:
                        mid = (bid + ask) / 2
            return {"mid": mid, "bid": bid, "ask": ask, "error": None}
        return {"mid": None, "bid": None, "ask": None, "error": "invalid payload"}
