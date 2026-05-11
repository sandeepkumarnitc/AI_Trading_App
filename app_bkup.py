import streamlit as st
import pandas as pd
from kiteconnect import KiteConnect

# -----------------------------
# 🔐 CONFIG
# -----------------------------
API_KEY = "35clx8i5b5na7iz9"

# Load access token
with open("access_token.txt", "r") as f:
    ACCESS_TOKEN = f.read().strip()

kite = KiteConnect(api_key=API_KEY)
kite.set_access_token(ACCESS_TOKEN)

st.set_page_config(layout="wide")
st.title("📊 Nifty AI Trading Dashboard")

# -----------------------------
# 📊 FETCH NIFTY PRICE
# -----------------------------
NIFTY = "NSE:NIFTY 50"
ltp = kite.ltp(NIFTY)
price = ltp[NIFTY]["last_price"]

st.metric("Nifty Price", price)


# -----------------------------
# 📦 FETCH INSTRUMENTS (ONCE)
# -----------------------------
@st.cache_data
def get_instruments():
    instruments = kite.instruments("NFO")
    return pd.DataFrame(instruments)


df = get_instruments()

# -----------------------------
# 🎯 AUTO ATM STRIKE
# -----------------------------
atm_strike = round(price / 50) * 50
st.write(f"ATM Strike: {atm_strike}")

# -----------------------------
# 📅 GET NEAREST EXPIRY
# -----------------------------
nifty_options = df[
    (df["name"] == "NIFTY") &
    (df["instrument_type"].isin(["CE", "PE"]))
    ]

nearest_expiry = nifty_options["expiry"].min()


# -----------------------------
# 🔍 GET OPTION SYMBOL
# -----------------------------
def get_option_symbol(strike, option_type="CE"):
    option = nifty_options[
        (nifty_options["strike"] == strike) &
        (nifty_options["expiry"] == nearest_expiry) &
        (nifty_options["instrument_type"] == option_type)
        ]

    if not option.empty:
        return "NFO:" + option.iloc[0]["tradingsymbol"]
    else:
        return None


ce_symbol = get_option_symbol(atm_strike, "CE")
pe_symbol = get_option_symbol(atm_strike, "PE")


# -----------------------------
# 📊 FETCH OPTION PRICE
# -----------------------------
def get_ltp(symbol):
    try:
        data = kite.ltp(symbol)
        return data[symbol]["last_price"]
    except:
        return None


ce_price = get_ltp(ce_symbol) if ce_symbol else None
pe_price = get_ltp(pe_symbol) if pe_symbol else None

# -----------------------------
# 📊 DISPLAY OPTION DATA
# -----------------------------
col1, col2 = st.columns(2)

col1.metric("ATM CE", ce_symbol if ce_symbol else "N/A")
col1.metric("CE Price", ce_price if ce_price else "N/A")

col2.metric("ATM PE", pe_symbol if pe_symbol else "N/A")
col2.metric("PE Price", pe_price if pe_price else "N/A")

# -----------------------------
# 🧠 LOGIC ENGINE
# -----------------------------
EMA_44 = price - 100  # placeholder
VWAP = price - 50  # placeholder
recent_high = price + 20
recent_low = price - 100

# Bias
if price > EMA_44:
    bias = "🟢 Bullish"
else:
    bias = "🔴 Bearish"

# Breakout
if price > recent_high:
    breakout = "UPSIDE"
elif price < recent_low:
    breakout = "DOWNSIDE"
else:
    breakout = "NONE"

# Momentum
if abs(price - VWAP) > 40:
    momentum = "🔥 Strong"
elif abs(price - VWAP) > 20:
    momentum = "🟡 Moderate"
else:
    momentum = "⚠️ Weak"

# Phase
if breakout != "NONE" and momentum == "🔥 Strong":
    phase = "EXPANSION"
elif momentum == "⚠️ Weak":
    phase = "EXHAUSTION"
else:
    phase = "SETUP"

# Signal
if bias == "🟢 Bullish" and breakout == "UPSIDE":
    signal = "BUY CALL"
elif bias == "🔴 Bearish" and breakout == "DOWNSIDE":
    signal = "BUY PUT"
else:
    signal = "NO TRADE"

# Exit Logic
if phase == "EXHAUSTION":
    exit_signal = "EXIT"
else:
    exit_signal = "HOLD"

# -----------------------------
# 📊 DISPLAY SIGNALS
# -----------------------------
st.subheader("📊 AI Signals")

c1, c2, c3, c4 = st.columns(4)

c1.metric("Bias", bias)
c2.metric("Breakout", breakout)
c3.metric("Momentum", momentum)
c4.metric("Phase", phase)

st.subheader("📌 Trade Decision")

st.write(f"Signal: {signal}")
st.write(f"Exit Signal: {exit_signal}")

# -----------------------------
# 🛑 RISK MANAGEMENT
# -----------------------------
st.subheader("🛑 Risk Management")

entry = ce_price if signal == "BUY CALL" else pe_price
if entry:
    sl = entry * 0.85
    target = entry * 1.3

    st.write(f"Entry: {entry}")
    st.write(f"SL: {round(sl, 2)}")
    st.write(f"Target: {round(target, 2)}")
else:
    st.write("No valid trade")