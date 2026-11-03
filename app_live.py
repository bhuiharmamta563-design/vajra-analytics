"""Vajra Analytics (Clone) - LIVE version for Streamlit.
Chart tool only, not trading advice.
"""
from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf
from streamlit_autorefresh import st_autorefresh

st.set_page_config(page_title="Vajra Analytics LIVE", layout="wide")
st.title("VAJRA ANALYTICS (Clone) - Live")
st.caption("Chart tool only, not trading advice.")

# ---------- Sidebar ----------
st.sidebar.header("Data source")
source = st.sidebar.radio("Source", ["Yahoo (delayed)", "Upstox (live)", "Zerodha Kite (live)"])
refresh_sec = st.sidebar.slider("Refresh every (seconds)", 1, 30, 3)

st.sidebar.header("Option chain base levels")
cip = st.sidebar.number_input("CIP", value=23800.0, step=50.0)
same = st.sidebar.checkbox("Use CIP for PIP too", value=False)
pip = cip if same else st.sidebar.number_input("PIP", value=23800.0, step=50.0)

st.sidebar.header("Mode and zone size")
stock_mode = st.sidebar.checkbox("Stock Mode (tick for stocks)", value=False)
gap_pts = st.sidebar.number_input("Gap from CIP/PIP (points)", value=20.0)
width_pts = st.sidebar.number_input("Zone width (points)", value=20.0)
step_pts = st.sidebar.number_input("Zone 1 to Zone 2 distance (points)", value=40.0)
pct = st.sidebar.number_input("Stock mode base %", value=0.1, step=0.05)

if source.startswith("Yahoo"):
    symbol = st.sidebar.text_input("Yahoo ticker", value="^NSEI")
else:
    if source.startswith("Upstox"):
        symbol = st.sidebar.text_input("Upstox instrument key", value="NSE_INDEX|Nifty 50")
    else:
        symbol = st.sidebar.text_input("Kite symbol", value="NSE:NIFTY 50")
    candle_min = st.sidebar.selectbox("Candle size (minutes)", [1, 3, 5, 15], index=0)
    if st.sidebar.button("Clear collected ticks"):
        st.session_state.pop("ticks", None)

st_autorefresh(interval=refresh_sec * 1000, key="auto_refresh")


# ---------- Helpers ----------
def get_zones():
    if stock_mode:
        gap = width = cip * pct / 100
        step = cip * pct / 50
    else:
        gap, width, step = gap_pts, width_pts, step_pts
    return {
        "Supply 1 Zone": (cip + gap, cip + gap + width),
        "Supply 2 Zone": (cip + gap + step, cip + gap + step + width),
        "Demand 1 Zone": (pip - gap - width, pip - gap),
        "Demand 2 Zone": (pip - gap - step - width, pip - gap - step),
    }


def yahoo_candles(ticker):
    df = yf.download(ticker, period="1d", interval="1m", progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df.dropna()


@st.cache_resource
def kite_client():
    from kiteconnect import KiteConnect

    kite = KiteConnect(api_key=st.secrets["KITE_API_KEY"])
    kite.set_access_token(st.secrets["KITE_ACCESS_TOKEN"])
    return kite


def to_candles(ltp, minutes):
    ticks = st.session_state.setdefault("ticks", [])
    ticks.append((datetime.now(), ltp))
    df = pd.DataFrame(ticks, columns=["t", "p"]).set_index("t")
    ohlc = df["p"].resample(f"{minutes}min").ohlc()
    ohlc.columns = ["Open", "High", "Low", "Close"]
    return ohlc.dropna(), ltp


def kite_candles(sym, minutes):
    ltp = float(kite_client().ltp([sym])[sym]["last_price"])
    return to_candles(ltp, minutes)


def upstox_candles(instrument_key, minutes):
    import requests

    resp = requests.get(
        "https://api.upstox.com/v2/market-quote/ltp",
        params={"instrument_key": instrument_key},
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {st.secrets['UPSTOX_ACCESS_TOKEN']}",
        },
        timeout=5,
    )
    resp.raise_for_status()
    body = resp.json().get("data", {})
    if not body:
        raise ValueError("Upstox returned no data. Check the instrument key and token.")
    ltp = float(next(iter(body.values()))["last_price"])
    return to_candles(ltp, minutes)


# ---------- Fetch data ----------
zones = get_zones()
last_price = None
try:
    if source.startswith("Yahoo"):
        data = yahoo_candles(symbol)
        if not data.empty:
            last_price = float(data["Close"].iloc[-1])
    elif source.startswith("Upstox"):
        data, last_price = upstox_candles(symbol, candle_min)
    else:
        data, last_price = kite_candles(symbol, candle_min)
except KeyError:
    st.error("Broker keys missing. Add them in Streamlit Secrets. Access tokens must be renewed every day.")
    st.stop()
except Exception as e:
    st.error(f"Data error: {e}")
    st.stop()

# ---------- Show ----------
zone_colors = {
    "Supply 1 Zone": "#FF9800",
    "Supply 2 Zone": "#F44336",
    "Demand 1 Zone": "#00C853",
    "Demand 2 Zone": "#26A69A",
}

if data is None or data.empty:
    st.warning("No data yet. Market may be closed, or wait for the next refresh.")
else:
    fig = go.Figure(go.Candlestick(
        x=data.index, open=data["Open"], high=data["High"], low=data["Low"], close=data["Close"],
        increasing_line_color="#26a69a", increasing_fillcolor="#26a69a",
        decreasing_line_color="#ef5350", decreasing_fillcolor="#ef5350",
    ))
    for name, (lo, hi) in zones.items():
        c = zone_colors[name]
        fig.add_hrect(y0=lo, y1=hi, fillcolor=c, opacity=0.30, line_width=1, line_color=c)
        fig.add_annotation(
            xref="paper", x=1, y=(lo + hi) / 2, text=name, showarrow=False,
            xanchor="left", font=dict(color="white", size=11), bgcolor=c, borderpad=3,
        )
    fig.add_hline(y=cip, line_dash="dot", line_color="#EF5350",
                  annotation_text="CIP", annotation_position="top left")
    fig.add_hline(y=pip, line_dash="dot", line_color="#00C853",
                  annotation_text="PIP", annotation_position="bottom left")
    fig.add_hline(y=last_price, line_dash="dash", line_color="#2962FF", line_width=1)
    fig.update_layout(height=650, xaxis_rangeslider_visible=False,
                      margin=dict(l=10, r=120, t=30, b=10), uirevision="keep")
    st.plotly_chart(fig, use_container_width=True)

    c1, c2, c3 = st.columns(3)
    c1.metric("Last price", f"{last_price:,.2f}")
    c2.metric("CIP", f"{cip:g}")
    c3.metric("PIP", f"{pip:g}")

    for name, (lo, hi) in zones.items():
        if lo <= last_price <= hi:
            st.warning(f"Price is inside {name} ({lo:.2f} - {hi:.2f})")

    st.caption(f"Updated: {datetime.now().strftime('%H:%M:%S')} | Source: {source}")
