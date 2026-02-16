from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go


def polymarket_style_chart(
    ticks_df: pd.DataFrame,
    start_ts: int,
    end_ts: int,
    price_to_beat: float | None,
    final_price: float | None,
) -> go.Figure:
    fig = go.Figure()
    ymin = None
    ymax = None

    if not ticks_df.empty:
        df = ticks_df.copy()
        df["dt"] = pd.to_datetime(df["ts_ms"], unit="ms", utc=True)
        ymin = float(df["price"].min())
        ymax = float(df["price"].max())
        fig.add_trace(
            go.Scatter(
                x=df["dt"],
                y=df["price"],
                mode="lines",
                name="BTC/USD (RTDS Chainlink)",
                line={"width": 2},
            )
        )

    start_dt = pd.to_datetime(start_ts, unit="s", utc=True)
    end_dt = pd.to_datetime(end_ts, unit="s", utc=True)

    for x_val, color, name in [(start_dt, "orange", "start"), (end_dt, "red", "end")]:
        fig.add_shape(
            type="line",
            x0=x_val,
            x1=x_val,
            y0=0,
            y1=1,
            xref="x",
            yref="paper",
            line={"dash": "dash", "color": color, "width": 1.5},
        )
        fig.add_annotation(x=x_val, y=1, yref="paper", text=name, showarrow=False, yshift=10)

    if price_to_beat is not None:
        fig.add_hline(y=price_to_beat, line_dash="dot", line_color="orange", annotation_text="price_to_beat")
    if final_price is not None:
        fig.add_hline(y=final_price, line_dash="dot", line_color="green", annotation_text="final_price")

    if ymin is not None and ymax is not None and ymin != ymax:
        fig.update_yaxes(range=[ymin * 0.999, ymax * 1.001])

    fig.update_layout(height=420, margin={"l": 10, "r": 10, "t": 30, "b": 10}, template="plotly_dark")
    return fig


def equity_curve_chart(trades_df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    if not trades_df.empty:
        df = trades_df.copy()
        df["dt"] = pd.to_datetime(df["ts"], unit="s", utc=True)
        fig.add_trace(go.Scatter(x=df["dt"], y=df["equity"], mode="lines", name="equity"))
    fig.update_layout(height=280, margin={"l": 10, "r": 10, "t": 30, "b": 10})
    return fig
