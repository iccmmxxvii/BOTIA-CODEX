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
                payload = {
                    "type": "subscribe",
                    "topic": "crypto_prices_chainlink",
                    "symbols": [FIXED_SYMBOL],
                }
                ws.send(json.dumps(payload))
                self.stats.connected = True
                self.stats.last_err = "OK"

            def on_message(_ws: WebSocketApp, message: str) -> None:
                self.stats.last_msg_time = time.time()
                try:
                    data = json.loads(message)
                except json.JSONDecodeError:
                    return
                parsed = self._parse_message(data)
                if parsed:
                    self.out_queue.put(parsed)

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
    def _parse_message(data: dict[str, Any]) -> tuple[int, float] | None:
        def _extract(container: dict[str, Any]) -> tuple[int, float] | None:
            symbol = str(container.get("symbol", "")).lower()
            if symbol != FIXED_SYMBOL:
                return None
            ts = container.get("ts") or container.get("timestamp") or container.get("t")
            price = (
                container.get("price")
                or container.get("value")
                or container.get("p")
                or container.get("px")
            )
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

        if isinstance(data.get("data"), list):
            for item in data["data"]:
                if isinstance(item, dict):
                    parsed = _extract(item)
                    if parsed:
                        return parsed
        if isinstance(data.get("data"), dict):
            return _extract(data["data"])
        return _extract(data)
