from __future__ import annotations
from dataclasses import dataclass
import os


def _getenv(name: str, default: str | None = None) -> str | None:
    v = os.getenv(name)
    return v if (v is not None and str(v).strip() != "") else default


@dataclass(frozen=True)
class BotConfig:
    db_path: str

    gamma_base: str
    rtds_ws: str

    market_slug: str | None
    rtds_symbol: str

    paper_bet_usd: float
    paper_parallel_orders: int

    tick_interval_sec: int
    status_interval_sec: int
    run_minutes: int


def load_config() -> BotConfig:
    return BotConfig(
        db_path=_getenv("BOTIA_DB_PATH", "./data/botia.sqlite") or "./data/botia.sqlite",

        gamma_base=_getenv("GAMMA_BASE", "https://gamma-api.polymarket.com") or "https://gamma-api.polymarket.com",
        rtds_ws=_getenv("RTDS_WS", "wss://ws-live-data.polymarket.com") or "wss://ws-live-data.polymarket.com",

        market_slug=_getenv("MARKET_SLUG"),
        rtds_symbol=_getenv("RTDS_SYMBOL", "BTC") or "BTC",

        paper_bet_usd=float(_getenv("PAPER_BET_USD", "1.0") or "1.0"),
        paper_parallel_orders=int(_getenv("PAPER_PARALLEL_ORDERS", "10") or "10"),

        tick_interval_sec=int(_getenv("TICK_INTERVAL_SEC", "2") or "2"),
        status_interval_sec=int(_getenv("STATUS_INTERVAL_SEC", "900") or "900"),
        run_minutes=int(_getenv("RUN_MINUTES", "30") or "30"),
    )
