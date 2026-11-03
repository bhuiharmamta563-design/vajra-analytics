import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf
from plotly.subplots import make_subplots

st.set_page_config(page_title="VAJRA ANALYTICS", layout="wide", page_icon="⚡")

# ---------- TradingView-style palette ----------
THEMES = {
    "Dark": dict(bg="#131722", grid="#2a2e39", text="#d1d4dc", tmpl="plotly_dark"),
    "Light": dict(bg="#ffffff", grid="#e0e3eb", text="#131722", tmpl="plotly_white"),
}
UP, DOWN = "#26a69a", "#ef5350"

st.markdown(
    "<style>.block-container{padding-top:1.2rem;padding-bottom:0.5rem}</style>",
    unsafe_allow_html=True,
)

# ---------------- Sidebar ----------------
with st.sidebar:
    st.header("⚡ VAJRA ANALYTICS")
    preset = st.selectbox("Instrument", ["NIFTY 50", "BANKNIFTY", "Custom (stock)"])
    custom = ""
    if preset == "Custom (stock)":
        custom = st.text_input("NSE symbol (e.g. RELIANCE)", "RELIANCE").strip().upper()
    stock_mode = preset == "Custom (stock)"

    st.subheader("Option chain levels")
    d_cip, d_pip = {"NIFTY 50": (23300.0, 23200.0), "BANKNIFTY": (51500.0, 51000.0)}.get(
        preset, (3000.0, 2900.0))
    cip = st.number_input("CIP (Call important price)", value=d_cip, step=5.0)
    pip = st.number_input("PIP (Put important price)", value=d_pip, step=5.0)

    st.subheader("Zone size")
    if stock_mode:
        p1 = st.number_input("Zone 1 width (%)", value=0.5, step=0.1)
        p2 = st.number_input("Zone 2 width (%)", value=1.0, step=0.1)
        w1c, w2c, w1p, w2p = cip * p1 / 100, cip * p2 / 100, pip * p1 / 100, pip * p2 / 100
    else:
        w1 = st.number_input("Zone 1 width (points)", value=25.0, step=5.0)
        w2 = st.number_input("Zone 2 width (points)", value=50.0, step=5.0)
        w1c = w1p = w1
        w2c = w2p = w2

    st.subheader("Chart settings")
    interval = st.selectbox("Timeframe", ["1m", "5m", "15m", "30m", "1h", "1d"], index=2)
    chart_type = st.selectbox("Chart type", ["Candles", "Heikin Ashi", "OHLC bars", "Line"])
    theme = st.radio("Theme", list(THEMES), horizontal=True)
    height = st.slider("Chart height (px)", 400, 1100, 700, 50)
    bars = st.slider("Bars to show", 30, 500, 150, 10)
    show_zones = st.checkbox("Show zones", True)
    zone_op = st.slider("Zone opacity", 0.05, 0.6, 0.22, 0.01)
    show_vol = st.checkbox("Volume", True)
    ema_on = st.multiselect("EMA", [9, 20, 50, 200], default=[20])
    show_last = st.checkbox("Last price line", True)
    refresh = st.button("🔄 Refresh data", use_container_width=True)

T = THEMES[theme]
ticker = {"NIFTY 50": "^NSEI", "BANKNIFTY": "^NSEBANK"}.get(preset, f"{custom}.NS")
period = {"1m": "5d", "5m": "30d", "15m": "30d", "30m": "60d", "1h": "180d", "1d": "2y"}[interval]


@st.cache_data(ttl=60, show_spinner="Data aa raha hai...")
def load(tkr, period, interval):
    df = yf.download(tkr, period=period, interval=interval, progress=False, auto_adjust=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df.dropna()


def heikin_ashi(d):
    ha = d.copy()
    ha["Close"] = (d["Open"] + d["High"] + d["Low"] + d["Close"]) / 4
    o = [(d["Open"].iloc[0] + d["Close"].iloc[0]) / 2]
    for i in range(1, len(d)):
        o.append((o[-1] + ha["Close"].iloc[i - 1]) / 2)
    ha["Open"] = o
    ha["High"] = pd.concat([d["High"], ha["Open"], ha["Close"]], axis=1).max(axis=1)
    ha["Low"] = pd.concat([d["Low"], ha["Open"], ha["Close"]], axis=1).min(axis=1)
    return ha


def build_fig(df, full, cip, pip, w1c, w2c, w1p, w2p):
    rows = 2 if show_vol and "Volume" in df and df["Volume"].sum() > 0 else 1
    fig = make_subplots(rows=rows, cols=1, shared_xaxes=True, vertical_spacing=0.02,
                        row_heights=[0.8, 0.2] if rows == 2 else [1.0])
    src = heikin_ashi(df) if chart_type == "Heikin Ashi" else df

    if chart_type == "Line":
        fig.add_trace(go.Scatter(x=df.index, y=df["Close"], mode="lines",
                                 line=dict(color="#2962ff", width=2), name="Close"), row=1, col=1)
    elif chart_type == "OHLC bars":
        fig.add_trace(go.Ohlc(x=src.index, open=src["Open"], high=src["High"], low=src["Low"],
                              close=src["Close"], increasing_line_color=UP,
                              decreasing_line_color=DOWN, name="Price"), row=1, col=1)
    else:
        fig.add_trace(go.Candlestick(x=src.index, open=src["Open"], high=src["High"],
                                     low=src["Low"], close=src["Close"],
                                     increasing_line_color=UP, increasing_fillcolor=UP,
                                     decreasing_line_color=DOWN, decreasing_fillcolor=DOWN,
                                     name="Price"), row=1, col=1)

    colors = {9: "#f9a825", 20: "#2962ff", 50: "#ab47bc", 200: "#e91e63"}
    for n in ema_on:
        e = full["Close"].ewm(span=n, adjust=False).mean().loc[df.index]
        fig.add_trace(go.Scatter(x=df.index, y=e, mode="lines", name=f"EMA {n}",
                                 line=dict(color=colors[n], width=1.3)), row=1, col=1)

    if rows == 2:
        vcol = np.where(df["Close"] >= df["Open"], UP, DOWN)
        fig.add_trace(go.Bar(x=df.index, y=df["Volume"], marker_color=vcol, opacity=0.6,
                             name="Volume", showlegend=False), row=2, col=1)

    # ----- Zones + CIP/PIP -----
    if show_zones:
        zones = [("Supply 2", cip + w1c, cip + w2c, "#ef5350"),
                 ("Supply 1", cip, cip + w1c, "#ff9800"),
                 ("Demand 1", pip - w1p, pip, "#26a69a"),
                 ("Demand 2", pip - w2p, pip - w1p, "#00897b")]
        for name, lo, hi, col in zones:
            fig.add_hrect(y0=lo, y1=hi, fillcolor=col, opacity=zone_op, line_width=0,
                          row=1, col=1, annotation_text=f"{name}  {lo:,.0f}–{hi:,.0f}",
                          annotation_position="top left",
                          annotation_font=dict(size=11, color=T["text"]))
        fig.add_hline(y=cip, line_dash="dash", line_color="#ff9800", line_width=1,
                      row=1, col=1, annotation_text="CIP", annotation_position="bottom right")
        fig.add_hline(y=pip, line_dash="dash", line_color="#26a69a", line_width=1,
                      row=1, col=1, annotation_text="PIP", annotation_position="top right")

    ltp, prev = float(df["Close"].iloc[-1]), float(df["Open"].iloc[-1])
    if show_last:
        fig.add_hline(y=ltp, line_dash="dot", line_width=1,
                      line_color=UP if ltp >= prev else DOWN, row=1, col=1,
                      annotation_text=f"{ltp:,.2f}", annotation_position="right",
                      annotation_font=dict(color="white", size=11),
                      annotation_bgcolor=UP if ltp >= prev else DOWN)

    # ----- Y range: price + zones so everything is visible -----
    lo_y = min(df["Low"].min(), pip - w2p if show_zones else df["Low"].min())
    hi_y = max(df["High"].max(), cip + w2c if show_zones else df["High"].max())
    pad = (hi_y - lo_y) * 0.04

    fig.update_layout(
        template=T["tmpl"], paper_bgcolor=T["bg"], plot_bgcolor=T["bg"],
        font=dict(color=T["text"]), height=height, margin=dict(l=8, r=8, t=30, b=8),
        dragmode="pan", hovermode="x unified", xaxis_rangeslider_visible=False,
        legend=dict(orientation="h", y=1.02, x=0), uirevision=f"{ticker}-{interval}",
        newshape=dict(line_color="#ffeb3b"),
    )
    breaks = [dict(bounds=["sat", "mon"])]
    if interval != "1d":
        breaks.append(dict(bounds=[15.5, 9.25], pattern="hour"))   # NSE hours (IST)
    fig.update_xaxes(showgrid=True, gridcolor=T["grid"], rangebreaks=breaks, showspikes=True,
                     spikemode="across", spikesnap="cursor", spikethickness=1,
                     spikedash="dot", spikecolor="#9598a1")
    fig.update_yaxes(showgrid=True, gridcolor=T["grid"], side="right", showspikes=True,
                     spikemode="across", spikethickness=1, spikedash="dot", spikecolor="#9598a1")
    fig.update_yaxes(range=[lo_y - pad, hi_y + pad], row=1, col=1)
    return fig


if refresh:
    st.cache_data.clear()

full = load(ticker, period, interval)
if full.empty:
    st.error(f"'{ticker}' ka data nahi mila. Symbol ya timeframe check karo.")
    st.stop()
df = full.tail(bars)

if pip >= cip:
    st.warning("Normally PIP, CIP se neeche hota hai. Values check kar lo.")

# ---------- Header strip ----------
ltp = float(df["Close"].iloc[-1])
chg = ltp - float(full["Close"].iloc[-2]) if len(full) > 1 else 0.0
h1, h2, h3, h4 = st.columns([2, 1, 1, 1])
h1.subheader(f"{ticker}  ·  {interval}")
h2.metric("LTP", f"{ltp:,.2f}", f"{chg:+,.2f}")
h3.metric("To CIP", f"{cip - ltp:,.1f}")
h4.metric("To PIP", f"{ltp - pip:,.1f}")

fig = build_fig(df, full, cip, pip, w1c, w2c, w1p, w2p)

config = {
    "scrollZoom": True,            # mouse wheel / pinch zoom
    "displaylogo": False,
    "doubleClick": "reset+autosize",
    "displayModeBar": True,
    "modeBarButtonsToAdd": ["drawline", "drawopenpath", "drawrect", "eraseshape"],
    "modeBarButtonsToRemove": ["lasso2d", "select2d"],
    "toImageButtonOptions": {"format": "png", "filename": "vajra_chart", "scale": 2},
}
st.plotly_chart(fig, width="stretch", config=config)

st.caption(
    "🖱️ Wheel/pinch = zoom · Drag = pan · Double-click = reset · Toolbar: 🔍+ / 🔍− zoom, "
    "Autoscale, Draw line/rect, Camera = PNG · ⛶ Fullscreen: chart par hover karke "
    "upar-right ka expand icon dabao."
)

if ltp > cip + w2c:
    st.error("🚀 Price Supply 2 ke upar — strong breakout")
elif ltp > cip:
    st.warning("📈 Price Supply zone ke andar — resistance area")
elif ltp < pip - w2p:
    st.error("🔻 Price Demand 2 ke neeche — strong breakdown")
elif ltp < pip:
    st.success("📉 Price Demand zone ke andar — support area")
else:
    st.info("↔️ Price PIP aur CIP ke beech (range-bound)")
st.caption("Sirf educational use ke liye. Ye financial advice nahi hai.")

