from __future__ import annotations
import json
import threading
import time
from dataclasses import dataclass
from typing import Callable

import websocket  # websocket-client


@dataclass
class RtdsState:
    connected: bool = False
    last_msg_ms: int = 0
    last_price: float | None = None
    last_price_ms: int | None = None
    last_error: str | None = None


class RtdsClient:
    """RTDS WebSocket base: wss://ws-live-data.polymarket.com
    Subscribe crypto prices: channel=rtds, action=subscribe, subscriptions=["cryptoPrices:BTC"].
    """

    def __init__(self, ws_url: str, symbol: str, on_tick: Callable[[int, float], None]):
        self.ws_url = ws_url
        self.symbol = symbol.upper()
        self.on_tick = on_tick
        self.state = RtdsState()
        self._ws: websocket.WebSocketApp | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        try:
            if self._ws:
                self._ws.close()
        except Exception:
            pass

    def _run(self) -> None:
        def on_open(ws):
            self.state.connected = True
            self.state.last_error = None
            sub = {
                "auth": "",
                "channel": "rtds",
                "action": "subscribe",
                "subscriptions": [f"cryptoPrices:{self.symbol}"],
            }
            ws.send(json.dumps(sub))

        def on_message(ws, message: str):
            self.state.last_msg_ms = int(time.time() * 1000)
            try:
                obj = json.loads(message)
            except Exception:
                return

            topic = obj.get("topic", "")
            payload = obj.get("payload") or {}
            if isinstance(topic, str) and topic.upper() == f"CRYPTOPRICES:{self.symbol}".upper():
                price = payload.get("price")
                ts = payload.get("time")
                if isinstance(price, (int, float)):
                    ts_ms = int(ts) if isinstance(ts, (int, float)) else int(time.time() * 1000)
                    self.state.last_price = float(price)
                    self.state.last_price_ms = ts_ms
                    self.on_tick(ts_ms, float(price))

        def on_error(ws, error):
            self.state.last_error = str(error)
            self.state.connected = False

        def on_close(ws, code, reason):
            self.state.connected = False

        while not self._stop.is_set():
            try:
                self._ws = websocket.WebSocketApp(
                    self.ws_url,
                    on_open=on_open,
                    on_message=on_message,
                    on_error=on_error,
                    on_close=on_close,
                )
                self._ws.run_forever(ping_interval=20, ping_timeout=10)
            except Exception as e:
                self.state.last_error = str(e)
                self.state.connected = False
            time.sleep(3)
