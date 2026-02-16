from __future__ import annotations

import numpy as np
import pandas as pd


def _lin_slope(y: np.ndarray) -> float:
    if len(y) < 2:
        return 0.0
    x = np.arange(len(y), dtype=float)
    denom = ((x - x.mean()) ** 2).sum()
    if denom == 0:
        return 0.0
    num = ((x - x.mean()) * (y - y.mean())).sum()
    return float(num / denom)


def _max_drawdown(series: np.ndarray) -> float:
    if len(series) == 0:
        return 0.0
    peak = np.maximum.accumulate(series)
    dd = (series - peak) / np.where(peak == 0, np.nan, peak)
    return float(np.nanmin(dd)) if np.isfinite(dd).any() else 0.0


def build_features(ticks_df: pd.DataFrame, ref_ts_s: int) -> dict[str, float]:
    """Build robust feature vector using data up to ref_ts_s.

    ticks_df must include ts_ms, price sorted ascending.
    """
    if ticks_df.empty:
        return {}

    end_ms = ref_ts_s * 1000
    df = ticks_df[ticks_df["ts_ms"] <= end_ms].copy()
    if df.empty:
        return {}

    df["ret"] = df["price"].pct_change().fillna(0.0)
    last_price = float(df["price"].iloc[-1])

    def ret_horizon(sec: int) -> float:
        cutoff = end_ms - sec * 1000
        sub = df[df["ts_ms"] >= cutoff]
        if len(sub) < 2:
            return 0.0
        p0 = float(sub["price"].iloc[0])
        p1 = float(sub["price"].iloc[-1])
        return (p1 / p0 - 1) if p0 else 0.0

    def vol_horizon(sec: int) -> float:
        cutoff = end_ms - sec * 1000
        sub = df[df["ts_ms"] >= cutoff]
        if len(sub) < 3:
            return 0.0
        return float(sub["ret"].std(ddof=0) or 0.0)

    def slope_horizon(sec: int) -> float:
        cutoff = end_ms - sec * 1000
        sub = df[df["ts_ms"] >= cutoff]
        if len(sub) < 3:
            return 0.0
        return _lin_slope(sub["price"].to_numpy())

    cutoff60 = end_ms - 60 * 1000
    sub60 = df[df["ts_ms"] >= cutoff60]
    prices60 = sub60["price"].to_numpy() if not sub60.empty else np.array([])

    range60 = 0.0
    dd60 = 0.0
    if len(prices60) >= 2:
        pmin = np.min(prices60)
        pmax = np.max(prices60)
        range60 = float((pmax - pmin) / pmin) if pmin else 0.0
        dd60 = _max_drawdown(prices60)

    rolling_mean = float(df["ret"].tail(60).mean()) if len(df) >= 2 else 0.0
    rolling_std = float(df["ret"].tail(60).std(ddof=0)) if len(df) >= 3 else 0.0
    z_ret = 0.0
    if rolling_std > 1e-12:
        z_ret = float((df["ret"].iloc[-1] - rolling_mean) / rolling_std)

    ts = pd.to_datetime(ref_ts_s, unit="s", utc=True)
    hour_utc = float(ts.hour)

    return {
        "last_price": last_price,
        "r_1s": ret_horizon(1),
        "r_5s": ret_horizon(5),
        "r_15s": ret_horizon(15),
        "r_60s": ret_horizon(60),
        "vol_15s": vol_horizon(15),
        "vol_60s": vol_horizon(60),
        "slope_30s": slope_horizon(30),
        "slope_60s": slope_horizon(60),
        "range_60s": range60,
        "max_drawdown_60s": dd60,
        "z_ret": z_ret,
        "hour_utc": hour_utc,
    }


def episodes_to_training_set(episodes_df: pd.DataFrame, ticks_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    if episodes_df.empty or ticks_df.empty:
        return pd.DataFrame(), pd.Series(dtype=int)

    rows = []
    labels = []
    for _, ep in episodes_df.iterrows():
        feat = build_features(ticks_df, int(ep["start_ts"]))
        if not feat:
            continue
        rows.append(feat)
        labels.append(int(ep["label"]))

    if not rows:
        return pd.DataFrame(), pd.Series(dtype=int)
    x = pd.DataFrame(rows)
    y = pd.Series(labels, dtype=int)
    return x, y
