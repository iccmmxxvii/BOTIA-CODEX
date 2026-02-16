from __future__ import annotations

import time
from queue import Queue

import pandas as pd
import streamlit as st
from streamlit_autorefresh import st_autorefresh

from core.clob_pricing import CLOBPricing
from core.engine import Engine
from core.features import build_features
from core.gamma_api import GammaAPI
from core.model import EpisodeModel
from core.plotting import equity_curve_chart, polymarket_style_chart
from core.rtds_client import RTDSClient
from core.storage import Storage
from core.utils import FIXED_SLUG, RuntimeStats

st.set_page_config(page_title="Polymarket BTC 5m", layout="wide")
st.title("Polymarket BTC 5 Minute Up or Down (Fixed)")
st.caption(f"Slug fijo: `{FIXED_SLUG}`")

if "init_done" not in st.session_state:
    st.session_state.init_done = True
    st.session_state.tick_queue = Queue()
    st.session_state.ws_stats = RuntimeStats()
    st.session_state.storage = Storage("data.db")
    st.session_state.model = EpisodeModel("model.joblib", "model_meta.json")
    st.session_state.engine = Engine(
        st.session_state.storage,
        st.session_state.model,
        st.session_state.tick_queue,
    )
    st.session_state.gamma = GammaAPI(ttl_s=60)
    st.session_state.clob = CLOBPricing()
    st.session_state.ws_client = RTDSClient(st.session_state.tick_queue, st.session_state.ws_stats)
    st.session_state.ws_client.start()

engine: Engine = st.session_state.engine
storage: Storage = st.session_state.storage
model: EpisodeModel = st.session_state.model
gamma: GammaAPI = st.session_state.gamma
clob: CLOBPricing = st.session_state.clob
ws_stats: RuntimeStats = st.session_state.ws_stats

st_autorefresh(interval=3000, key="page_refresh")

drained = engine.drain_ticks(max_items=5000)
if drained:
    engine.log(f"drained_ticks={drained}")

created_eps = engine.build_missing_episodes()
if created_eps:
    engine.log(f"episodes_created={created_eps}")

if time.time() % 30 < 3:
    metrics = engine.maybe_train()
    if metrics:
        engine.log(f"model trained: {metrics}")

market_meta = gamma.get_market(FIXED_SLUG)
token_map = gamma.map_up_down_tokens(market_meta)
up_token = token_map.get("up_token")

mkt = engine.current_market_math()
fig = polymarket_style_chart(
    mkt["ticks"],
    mkt["start_ts"],
    mkt["end_ts"],
    mkt["price_to_beat"],
    mkt["final_price"],
)

st.subheader("A) Polymarket-style chart")
st.plotly_chart(fig, width="stretch")

last_price = float(mkt["ticks"]["price"].iloc[-1]) if not mkt["ticks"].empty else None
ws_dict = ws_stats.as_dict()
last_msg = (
    pd.to_datetime(ws_dict["last_msg_time"], unit="s", utc=True).isoformat()
    if ws_dict["last_msg_time"]
    else "N/A"
)

st.subheader("B) Métricas")
cols = st.columns(4)
cols[0].metric("Underlying last", f"{last_price:.2f}" if last_price else "N/A")
cols[1].metric("Price to beat", f"{mkt['price_to_beat']:.2f}" if mkt["price_to_beat"] else "N/A")
cols[2].metric("Final price", f"{mkt['final_price']:.2f}" if mkt["final_price"] else "N/A")
cols[3].metric("Outcome", mkt["outcome"] or "N/A")

cols2 = st.columns(4)
cols2[0].metric("WS status", "connected" if ws_dict["connected"] else "reconnecting")
cols2[1].metric("WS last_msg_time", last_msg)
cols2[2].metric("WS reconnect_count", ws_dict["reconnect_count"])
cols2[3].metric("Ticks buffer size", st.session_state.tick_queue.qsize())
st.caption(f"WS last_err: {ws_dict['last_err']}")

st.subheader("C) Modelo IA")
feat = build_features(mkt["ticks"], mkt["start_ts"])
p_up_ml = model.predict_p_up(feat) if feat else None
p_up_mkt = None
price_info = {"error": ""}
if up_token:
    price_info = clob.get_token_mid(up_token)
    p_up_mkt = price_info.get("mid")

status = model.status()
signal, edge = engine.decide_signal(p_up_ml, p_up_mkt, status.healthy)

mc1, mc2, mc3, mc4 = st.columns(4)
mc1.metric("p_up_ml", f"{p_up_ml:.4f}" if p_up_ml is not None else "N/A")
mc2.metric("p_up_mkt", f"{p_up_mkt:.4f}" if p_up_mkt is not None else "N/A")
mc3.metric("edge", f"{edge:.4f}" if edge is not None else "N/A")
mc4.metric("señal", signal)

st.write(
    {
        "model_healthy": status.healthy,
        "reason": status.reason,
        "last_trained": status.last_trained,
        "n_samples": status.n_samples,
        "metrics": status.metrics,
        "up_token": up_token,
        "clob_error": price_info.get("error"),
    }
)

if not up_token:
    st.warning("No se pudo mapear token UP/YES desde Gamma. Señal forzada a HOLD.")

engine.paper_trade_step(signal, last_price, p_up_ml, p_up_mkt, edge)

st.subheader("D) Paper Trading")
trades = storage.paper_trades_df(limit=500)
last_equity = float(trades["equity"].iloc[-1]) if not trades.empty else engine.paper_equity
cum_pnl = float(trades["pnl"].sum()) if not trades.empty else 0.0
pc1, pc2, pc3 = st.columns(3)
pc1.metric("equity", f"{last_equity:.2f}")
pc2.metric("pnl", f"{cum_pnl:.2f}")
pc3.metric("risk status", "DRY-RUN ONLY")
st.plotly_chart(equity_curve_chart(trades), width="stretch")
st.dataframe(trades.tail(20), width="stretch")

st.subheader("E) Heartbeat & Logs")
st.write(
    {
        "uptime_s": round(ws_dict["uptime_s"], 1),
        "last_err": ws_dict["last_err"],
        "reconnect_count": ws_dict["reconnect_count"],
        "drained_last_cycle": drained,
        "episodes_created_last_cycle": created_eps,
    }
)
st.text("\n".join(engine.logs[-30:]) if engine.logs else "No logs yet")
