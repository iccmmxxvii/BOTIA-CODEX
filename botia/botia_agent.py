from __future__ import annotations
import time
from dotenv import load_dotenv

from core.config import load_config
from core.storage import connect, init_db
from core.log import log_line, update_status
from core.polymarket.gamma import GammaClient
from core.polymarket.rtds import RtdsClient
from core.engine import engine_tick, insert_tick


def main() -> None:
    load_dotenv()
    cfg = load_config()

    if not cfg.market_slug:
        raise RuntimeError("Define MARKET_SLUG en .env (ej: btc-updown-5m-1771309500)")

    con = connect(cfg.db_path)
    init_db(con)

    gamma = GammaClient(cfg.gamma_base)

    # RTDS -> persist ticks
    def _on_tick(ts_ms: int, price: float) -> None:
        insert_tick(con, ts_ms, cfg.rtds_symbol, price)

    rtds = RtdsClient(cfg.rtds_ws, cfg.rtds_symbol, _on_tick)
    rtds.start()
    log_line(f"[AGENT] RTDS started ws={cfg.rtds_ws} symbol={cfg.rtds_symbol}")

    start = time.time()
    next_status = time.time()

    run_seconds = max(60, cfg.run_minutes * 60)

    try:
        while (time.time() - start) < run_seconds:
            # tick engine
            try:
                engine_tick(
                    con,
                    gamma,
                    market_slug=cfg.market_slug,
                    symbol=cfg.rtds_symbol,
                    stake=cfg.paper_bet_usd,
                    parallel_orders=cfg.paper_parallel_orders,
                )
            except Exception as e:
                log_line(f"[AGENT] engine_tick error: {e}")

            # status cada N segundos
            if time.time() >= next_status:
                next_status = time.time() + cfg.status_interval_sec
                status_txt = f"""# BOTIA STATUS

- Last update: {time.strftime("%Y-%m-%d %H:%M:%S")}
- Market slug: {cfg.market_slug}
- RTDS connected: {rtds.state.connected}
- Last price: {rtds.state.last_price}
- Last msg ms: {rtds.state.last_msg_ms}
- Last error: {rtds.state.last_error}

Next: keep running paper + verify trades resolved after endDate.
"""
                update_status(status_txt)
                log_line("[AGENT] STATUS.md updated")

            time.sleep(max(1, cfg.tick_interval_sec))
    finally:
        rtds.stop()
        log_line("[AGENT] stopped")


if __name__ == "__main__":
    main()
