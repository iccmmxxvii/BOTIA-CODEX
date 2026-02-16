from __future__ import annotations

import time
from queue import Empty, Queue
from typing import Any

import pandas as pd

from core.features import episodes_to_training_set
from core.model import EpisodeModel
from core.storage import Storage
from core.utils import FIXED_SLUG, first_on_or_after, parse_end_ts_from_slug


class Engine:
    def __init__(self, storage: Storage, model: EpisodeModel, tick_queue: Queue) -> None:
        self.storage = storage
        self.model = model
        self.tick_queue = tick_queue
        self.logs: list[str] = []
        self.paper_equity = 1000.0
        self.paper_position = 0.0
        self.paper_entry = None

    def log(self, msg: str) -> None:
        line = f"{pd.Timestamp.utcnow().isoformat()} | {msg}"
        self.logs.append(line)
        self.logs = self.logs[-200:]

    def drain_ticks(self, max_items: int = 1000) -> int:
        rows = []
        for _ in range(max_items):
            try:
                rows.append(self.tick_queue.get_nowait())
            except Empty:
                break
        if rows:
            self.storage.insert_ticks(rows)
        return len(rows)

    def build_missing_episodes(self) -> int:
        bounds = self.storage.tick_bounds_s()
        if not bounds:
            return 0

        min_tick_s, max_tick_s = bounds
        latest_ep_end = self.storage.latest_episode_end()

        if latest_ep_end is None:
            start_end_ts = ((min_tick_s // 300) * 300) + 300
        else:
            start_end_ts = latest_ep_end + 300

        max_complete_end_ts = (max_tick_s // 300) * 300
        if start_end_ts > max_complete_end_ts:
            return 0

        count = 0
        for end_ts in range(start_end_ts, max_complete_end_ts + 1, 300):
            start_ts = end_ts - 300
            s = self.storage.get_tick_on_or_after_else_before(start_ts)
            e = self.storage.get_tick_on_or_after_else_before(end_ts)
            if not s or not e:
                continue
            label = 1 if e[1] >= s[1] else 0
            self.storage.upsert_episode(start_ts, end_ts, s[1], e[1], label)
            count += 1
        return count

    def maybe_train(self) -> dict[str, float]:
        episodes = self.storage.episodes_df(limit=3000)
        ticks = self.storage.get_ticks_df(limit=20000)
        x, y = episodes_to_training_set(episodes, ticks)
        if len(x) < 80:
            return {}
        return self.model.train(x, y)

    def current_market_math(self) -> dict[str, Any]:
        end_ts = parse_end_ts_from_slug(FIXED_SLUG)
        start_ts = end_ts - 300
        ticks = self.storage.get_ticks_df(limit=50000)
        points = list(ticks[["ts_ms", "price"]].itertuples(index=False, name=None)) if not ticks.empty else []
        ptb = first_on_or_after(points, start_ts)
        final = first_on_or_after(points, end_ts)
        out = None
        if ptb and final:
            out = "Up" if final[1] >= ptb[1] else "Down"
        return {
            "start_ts": start_ts,
            "end_ts": end_ts,
            "price_to_beat": ptb[1] if ptb else None,
            "final_price": final[1] if final else None,
            "outcome": out,
            "ticks": ticks,
        }

    def decide_signal(
        self,
        p_up_ml: float | None,
        p_up_mkt: float | None,
        model_healthy: bool,
        edge_threshold: float = 0.03,
    ) -> tuple[str, float | None]:
        if p_up_ml is None or p_up_mkt is None:
            return "HOLD", None
        edge = p_up_ml - p_up_mkt
        if not model_healthy:
            return "HOLD", edge
        if edge >= edge_threshold:
            return "BUY_UP", edge
        if edge <= -edge_threshold:
            return "BUY_DOWN", edge
        return "HOLD", edge

    def paper_trade_step(
        self,
        signal: str,
        underlying_price: float | None,
        p_up_ml: float | None,
        p_up_mkt: float | None,
        edge: float | None,
    ) -> None:
        if underlying_price is None:
            return
        ts = int(time.time())
        qty = 0.0
        pnl = 0.0
        note = "dry-run"

        if signal == "BUY_UP" and self.paper_position <= 0:
            if self.paper_position < 0 and self.paper_entry is not None:
                pnl = (self.paper_entry - underlying_price) * abs(self.paper_position)
                self.paper_equity += pnl
            self.paper_position = 1.0
            self.paper_entry = underlying_price
            qty = 1.0
            note = "open long"
        elif signal == "BUY_DOWN" and self.paper_position >= 0:
            if self.paper_position > 0 and self.paper_entry is not None:
                pnl = (underlying_price - self.paper_entry) * abs(self.paper_position)
                self.paper_equity += pnl
            self.paper_position = -1.0
            self.paper_entry = underlying_price
            qty = -1.0
            note = "open short"

        self.storage.insert_trade(
            ts,
            signal,
            underlying_price,
            p_up_ml,
            p_up_mkt,
            edge,
            qty,
            pnl,
            self.paper_equity,
            note,
        )
