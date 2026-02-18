from __future__ import annotations
import sqlite3

from core.log import log_line
from core.polymarket.gamma import extract_price_to_beat, to_json_str
from core.utils.timeutils import iso_to_ms, now_ms, nearest_tick


def insert_tick(con: sqlite3.Connection, ts_ms: int, symbol: str, price: float) -> None:
    con.execute(
        "INSERT INTO price_ticks (ts_ms, symbol, price) VALUES (?, ?, ?)",
        (ts_ms, symbol.upper(), float(price)),
    )
    con.commit()


def _latest_price(con: sqlite3.Connection, symbol: str) -> tuple[int, float] | None:
    row = con.execute(
        "SELECT ts_ms, price FROM price_ticks WHERE symbol=? ORDER BY ts_ms DESC LIMIT 1",
        (symbol.upper(),),
    ).fetchone()
    if not row:
        return None
    return int(row[0]), float(row[1])


def _unresolved_trade_ids(con: sqlite3.Connection, market_slug: str) -> set[int]:
    rows = con.execute(
        """
        SELECT t.id
        FROM paper_trades t
        LEFT JOIN paper_results r ON r.trade_id = t.id
        WHERE t.market_slug = ? AND r.id IS NULL
        """,
        (market_slug,),
    ).fetchall()
    return {int(r[0]) for r in rows}


def engine_tick(
    con: sqlite3.Connection,
    gamma,
    *,
    market_slug: str,
    symbol: str,
    stake: float,
    parallel_orders: int,
) -> None:
    ts = now_ms()
    con.execute("INSERT INTO heartbeat (ts_ms, status, detail) VALUES (?, ?, ?)", (ts, "ok", "engine_tick"))

    market = gamma.get_market_by_slug(market_slug)
    con.execute(
        "INSERT INTO market_snapshots (ts_ms, market_slug, raw_json) VALUES (?, ?, ?)",
        (ts, market_slug, to_json_str(market)),
    )

    latest = _latest_price(con, symbol)
    if not latest:
        con.commit()
        return

    _, px = latest
    ptb = extract_price_to_beat(market)
    if ptb is None:
        con.commit()
        return

    unresolved = _unresolved_trade_ids(con, market_slug)
    if not unresolved:
        side = "UP" if px >= ptb else "DOWN"
        for _ in range(max(1, parallel_orders)):
            con.execute(
                "INSERT INTO paper_trades (ts_ms, market_slug, side, stake, price_to_beat, note) VALUES (?, ?, ?, ?, ?, ?)",
                (ts, market_slug, side, float(stake), float(ptb), f"entry_px={px}"),
            )
        log_line(f"[ENGINE] opened {max(1, parallel_orders)} paper trades side={side} ptb={ptb} px={px}")

    end_ms = iso_to_ms(str(market.get("endDate") or market.get("end_date") or ""))
    if end_ms is None or now_ms() < end_ms:
        con.commit()
        return

    ticks = con.execute(
        "SELECT ts_ms, price FROM price_ticks WHERE symbol=? ORDER BY ts_ms ASC",
        (symbol.upper(),),
    ).fetchall()
    nearest = nearest_tick(end_ms, [(int(t[0]), float(t[1])) for t in ticks])
    final_price = nearest[1] if nearest else px
    outcome = "UP" if final_price >= ptb else "DOWN"

    unresolved = _unresolved_trade_ids(con, market_slug)
    for trade_id in unresolved:
        row = con.execute("SELECT side, stake FROM paper_trades WHERE id=?", (trade_id,)).fetchone()
        if not row:
            continue
        side, trade_stake = str(row[0]).upper(), float(row[1])
        pnl = trade_stake if side == outcome else -trade_stake
        con.execute(
            "INSERT INTO paper_results (trade_id, resolved_ms, final_price, outcome, pnl) VALUES (?, ?, ?, ?, ?)",
            (trade_id, now_ms(), float(final_price), outcome, pnl),
        )

    con.commit()
