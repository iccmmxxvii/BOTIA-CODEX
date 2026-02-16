from __future__ import annotations

import json
import threading
import time
from queue import Queue
from typing import Any

from websocket import WebSocketApp

from core.utils import FIXED_SYMBOL, RTDS_WS_URL, RuntimeStats, safe_float


class RTDSClient:
    """Threaded WebSocket client for Polymarket RTDS crypto prices."""

    def __init__(self, out_queue: Queue, stats: RuntimeStats) -> None:
        self.out_queue = out_queue
        self.stats = stats
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()

    def _run_loop(self) -> None:
        backoff = 1
        while not self._stop_event.is_set():
            self.stats.connected = False

            def on_open(ws: WebSocketApp) -> None:
                subscribe_payload = {
                    "action": "subscribe",
                    "subscriptions": [
                        {
                            "topic": "crypto_prices_chainlink",
                            "type": "*",
                            "filters": json.dumps({"symbol": FIXED_SYMBOL}),
                        },
                        {
                            "topic": "crypto_prices_chainlink",
                            "type": "*",
                            "filters": json.dumps({"symbol": "BTCUSD"}),
                        },
                    ],
                }
                ws.send(json.dumps(subscribe_payload))
                self.stats.connected = True
                self.stats.last_err = "OK"

            def on_message(ws: WebSocketApp, message: str) -> None:
                self.stats.last_msg_time = time.time()
                if isinstance(message, str) and message.lower() == "ping":
                    ws.send("pong")
                    return

                try:
                    data = json.loads(message)
                except json.JSONDecodeError:
                    return

                parsed = self._parse_message(data)
                for item in parsed:
                    self.out_queue.put(item)

            def on_error(_ws: WebSocketApp, error: Any) -> None:
                self.stats.last_err = str(error)
                self.stats.connected = False

            def on_close(_ws: WebSocketApp, _code: Any, _msg: Any) -> None:
                self.stats.connected = False

            ws = WebSocketApp(
                RTDS_WS_URL,
                on_open=on_open,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close,
            )
            ws.run_forever(ping_interval=5, ping_timeout=3)

            if self._stop_event.is_set():
                break

            self.stats.reconnect_count += 1
            time.sleep(backoff)
            backoff = min(backoff * 2, 20)

    @staticmethod
    def _extract_points(container: dict[str, Any]) -> list[tuple[int, float]]:
        points: list[tuple[int, float]] = []

        def parse_one(item: dict[str, Any]) -> tuple[int, float] | None:
            ts = item.get("ts") or item.get("timestamp") or item.get("t")
            price = item.get("price") or item.get("value") or item.get("p") or item.get("px")

            ts_ms = None
            if ts is not None:
                try:
                    ts_val = int(float(ts))
                    ts_ms = ts_val if ts_val > 10_000_000_000 else ts_val * 1000
                except (TypeError, ValueError):
                    ts_ms = None
            if ts_ms is None:
                ts_ms = int(time.time() * 1000)

            price_f = safe_float(price)
            if price_f is None:
                return None
            return ts_ms, price_f

        data = container.get("data")
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    parsed = parse_one(item)
                    if parsed:
                        points.append(parsed)
            return points
        if isinstance(data, dict):
            parsed = parse_one(data)
            return [parsed] if parsed else []

        parsed = parse_one(container)
        return [parsed] if parsed else []

    @classmethod
    def _parse_message(cls, data: dict[str, Any]) -> list[tuple[int, float]]:
        payload = data.get("payload")
        if isinstance(payload, dict):
            return cls._extract_points(payload)
        return cls._extract_points(data)
