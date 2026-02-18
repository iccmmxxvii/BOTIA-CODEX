from __future__ import annotations
import time
from pathlib import Path

LOG_PATH = Path("./logs/agent.log")
STATUS_PATH = Path("./STATUS.md")


def ensure_dirs() -> None:
    Path("./logs").mkdir(parents=True, exist_ok=True)
    Path("./data").mkdir(parents=True, exist_ok=True)


def log_line(msg: str) -> None:
    ensure_dirs()
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(f"[{ts}] {msg}\n")


def update_status(block: str) -> None:
    ensure_dirs()
    with open(STATUS_PATH, "w", encoding="utf-8") as f:
        f.write(block)
