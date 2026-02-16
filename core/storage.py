from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable

import pandas as pd

from core.utils import now_utc_iso


class Storage:
    def __init__(self, db_path: str = "data.db") -> None:
        self.db_path = Path(db_path)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL;")
        self._init_tables()

    def _init_tables(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ticks(
                ts_ms INTEGER PRIMARY KEY,
                price REAL
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS episodes(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                start_ts INTEGER,
                end_ts INTEGER,
                start_price REAL,
                end_price REAL,
                label INTEGER,
                created_at TEXT
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS paper_trades(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts INTEGER,
                action TEXT,
                price REAL,
                p_up_ml REAL,
                p_up_mkt REAL,
                edge REAL,
                qty REAL,
                pnl REAL,
                equity REAL,
                note TEXT
            )
            """
        )
        self.conn.commit()

    def insert_ticks(self, ticks: Iterable[tuple[int, float]]) -> int:
        rows = list(ticks)
        if not rows:
            return 0
        self.conn.executemany(
            "INSERT OR REPLACE INTO ticks(ts_ms, price) VALUES(?, ?)",
            rows,
        )
        self.conn.commit()
        return len(rows)

    def get_ticks_df(self, limit: int = 5000) -> pd.DataFrame:
        query = "SELECT ts_ms, price FROM ticks ORDER BY ts_ms DESC LIMIT ?"
        df = pd.read_sql_query(query, self.conn, params=(limit,))
        if df.empty:
            return df
        return df.sort_values("ts_ms").reset_index(drop=True)

    def get_tick_on_or_after_else_before(self, ts_s: int) -> tuple[int, float] | None:
        target_ms = ts_s * 1000
        cur = self.conn.cursor()
        cur.execute(
            "SELECT ts_ms, price FROM ticks WHERE ts_ms >= ? ORDER BY ts_ms ASC LIMIT 1",
            (target_ms,),
        )
        row = cur.fetchone()
        if row:
            return int(row[0]), float(row[1])
        cur.execute(
            "SELECT ts_ms, price FROM ticks WHERE ts_ms < ? ORDER BY ts_ms DESC LIMIT 1",
            (target_ms,),
        )
        row = cur.fetchone()
        if row:
            return int(row[0]), float(row[1])
        return None

    def upsert_episode(
        self,
        start_ts: int,
        end_ts: int,
        start_price: float,
        end_price: float,
        label: int,
    ) -> None:
        cur = self.conn.cursor()
        cur.execute(
            "SELECT id FROM episodes WHERE start_ts = ? AND end_ts = ? LIMIT 1",
            (start_ts, end_ts),
        )
        exists = cur.fetchone()
        if exists:
            return
        self.conn.execute(
            """
            INSERT INTO episodes(start_ts, end_ts, start_price, end_price, label, created_at)
            VALUES(?, ?, ?, ?, ?, ?)
            """,
            (start_ts, end_ts, start_price, end_price, label, now_utc_iso()),
        )
        self.conn.commit()

    def episodes_df(self, limit: int = 5000) -> pd.DataFrame:
        df = pd.read_sql_query(
            "SELECT * FROM episodes ORDER BY end_ts DESC LIMIT ?", self.conn, params=(limit,)
        )
        if df.empty:
            return df
        return df.sort_values("end_ts").reset_index(drop=True)

    def latest_episode_end(self) -> int | None:
        cur = self.conn.cursor()
        cur.execute("SELECT end_ts FROM episodes ORDER BY end_ts DESC LIMIT 1")
        row = cur.fetchone()
        return int(row[0]) if row else None

    def insert_trade(
        self,
        ts: int,
        action: str,
        price: float,
        p_up_ml: float | None,
        p_up_mkt: float | None,
        edge: float | None,
        qty: float,
        pnl: float,
        equity: float,
        note: str,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO paper_trades(ts, action, price, p_up_ml, p_up_mkt, edge, qty, pnl, equity, note)
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (ts, action, price, p_up_ml, p_up_mkt, edge, qty, pnl, equity, note),
        )
        self.conn.commit()

    def paper_trades_df(self, limit: int = 500) -> pd.DataFrame:
        df = pd.read_sql_query(
            "SELECT * FROM paper_trades ORDER BY ts DESC LIMIT ?", self.conn, params=(limit,)
        )
        if df.empty:
            return df
        return df.sort_values("ts").reset_index(drop=True)
