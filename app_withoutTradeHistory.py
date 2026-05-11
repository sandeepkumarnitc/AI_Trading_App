import streamlit as st
import pandas as pd
import datetime
from kiteconnect import KiteConnect

# ---------------- CONFIG ----------------
API_KEY = "35clx8i5b5na7iz9"

with open("access_token.txt", "r") as f:
    ACCESS_TOKEN = f.read().strip()

kite = KiteConnect(api_key=API_KEY)
kite.set_access_token(ACCESS_TOKEN)

st.set_page_config(layout="wide", page_title="AI Trading Assistant")

# ---------------- HEADER ----------------
st.markdown("## 📊 AI Options Trading Assistant")
st.caption("EMA + VWAP + Price Action + MTF Logic")

# ---------------- DATA FUNCTIONS ----------------
def get_data(interval):
    to_date = datetime.datetime.now()
    from_date = to_date - datetime.timedelta(days=5)

    data = kite.historical_data(
        instrument_token=256265,
        from_date=from_date,
        to_date=to_date,
        interval=interval
    )

    df = pd.DataFrame(data)
    df["date"] = pd.to_datetime(df["date"])
    df["EMA_44"] = df["close"].ewm(span=44, adjust=False).mean()
    return df

@st.cache_data
def get_instruments():
    return pd.DataFrame(kite.instruments("NFO"))

def get_fut_token(df):
    fut = df[(df["name"] == "NIFTY") & (df["instrument_type"] == "FUT")]
    expiry = fut["expiry"].min()
    return int(fut[fut["expiry"] == expiry].iloc[0]["instrument_token"])

def get_fut_data(token):
    to_date = datetime.datetime.now()
    from_date = to_date - datetime.timedelta(days=2)

    data = kite.historical_data(
        instrument_token=token,
        from_date=from_date,
        to_date=to_date,
        interval="5minute"
    )

    df = pd.DataFrame(data)
    df["date"] = pd.to_datetime(df["date"])
    return df

# ---------------- FETCH DATA ----------------
df5 = get_data("5minute")
df15 = get_data("15minute")

price = df5["close"].iloc[-1]
ema5 = df5["EMA_44"].iloc[-1]
ema15 = df15["EMA_44"].iloc[-1]
price15 = df15["close"].iloc[-1]

# ---------------- VWAP (FUTURES) ----------------
inst = get_instruments()
fut_token = get_fut_token(inst)
df_fut = get_fut_data(fut_token)

today = df_fut["date"].dt.date.iloc[-1]
df_today = df_fut[df_fut["date"].dt.date == today].copy()

df_today = df_today[df_today["volume"] > 0]
df_today["cum_vol"] = df_today["volume"].cumsum()
df_today["cum_val"] = (df_today["close"] * df_today["volume"]).cumsum()
df_today["VWAP"] = df_today["cum_val"] / df_today["cum_vol"]

vwap = df_today["VWAP"].iloc[-1] if not df_today.empty else None

# ---------------- STRUCTURE ----------------
recent_high = df5["high"].rolling(10).max().iloc[-2]
recent_low = df5["low"].rolling(10).min().iloc[-2]

# ---------------- 15 MIN TREND ----------------
if price15 > ema15:
    trend15 = "🟢 Bullish"
elif price15 < ema15:
    trend15 = "🔴 Bearish"
else:
    trend15 = "⚪ Sideways"

# ---------------- 5 MIN TREND ----------------
if price > ema5 and vwap and price > vwap:
    trend5 = "🟢 Bullish"
elif price < ema5 and vwap and price < vwap:
    trend5 = "🔴 Bearish"
else:
    trend5 = "⚪ Sideways"

# ---------------- BREAKDOWN ----------------
prev_close = df5["close"].iloc[-2]
prev_ema = df5["EMA_44"].iloc[-2]
breakdown = prev_close > prev_ema and price < ema5

# ---------------- ENTRY ----------------
last = df5.iloc[-1]
body = abs(last["close"] - last["open"])

if price > recent_high and body > 10:
    entry = "Breakout"
elif price <= ema5:
    entry = "Pullback"
else:
    entry = "Wait"

# ---------------- EXHAUSTION ----------------
range_size = recent_high - recent_low
exhaustion = abs(price - recent_high) < (0.2 * range_size)

# ---------------- CHOP ----------------
last5_range = df5["high"].iloc[-5:].max() - df5["low"].iloc[-5:].min()
chop = last5_range < 40

# ---------------- WEAK CANDLE ----------------
weak_candle = body < 5

# ---------------- SIGNAL ----------------
signal = "⚠️ WAIT"

if chop:
    signal = "⚠️ NO TRADE (CHOP)"

elif "Bearish" in trend15:
    if breakdown and not weak_candle:
        signal = "🔴 BUY PUT (STRONG)"

elif "Bullish" in trend15:
    if entry == "Breakout" and not exhaustion and not weak_candle:
        signal = "🟢 BUY CALL (STRONG)"

# ---------------- OPTIONS ----------------
def get_options(df, price):
    atm = round(price / 50) * 50
    strikes = [atm-100, atm-50, atm, atm+50, atm+100]

    opt = df[
        (df["name"]=="NIFTY") &
        (df["instrument_type"].isin(["CE","PE"]))
    ]

    expiry = opt["expiry"].min()
    opt = opt[opt["expiry"] == expiry]

    return opt[opt["strike"].isin(strikes)]

def get_prices(opt_df):
    prices = []
    for _, r in opt_df.iterrows():
        sym = "NFO:" + r["tradingsymbol"]
        try:
            ltp = kite.ltp(sym)
            prices.append(ltp[sym]["last_price"])
        except:
            prices.append(None)
    opt_df["price"] = prices
    return opt_df

opt_df = get_options(inst, price)
opt_df = get_prices(opt_df)

# ---------------- PICK STRIKE ----------------
def pick(opt_df, signal):
    if "CALL" in signal:
        return opt_df[opt_df["instrument_type"]=="CE"].sort_values("strike").iloc[2]
    elif "PUT" in signal:
        return opt_df[opt_df["instrument_type"]=="PE"].sort_values("strike").iloc[2]
    return None

selected = pick(opt_df, signal)

# ---------------- UI ----------------
col1, col2, col3 = st.columns(3)
col1.metric("Price", round(price,2))
col2.metric("EMA (5m)", round(ema5,2))
col3.metric("VWAP", round(vwap,2) if vwap else "N/A")

st.divider()

colA, colB, colC = st.columns(3)
colA.write(f"15m Trend: {trend15}")
colB.write(f"5m Trend: {trend5}")
colC.write(f"Chop: {'YES' if chop else 'NO'}")

st.write(f"Entry: {entry} | Weak Candle: {'YES' if weak_candle else 'NO'}")

st.divider()
st.subheader("🚀 Signal")
st.markdown(f"### {signal}")

# ---------------- TRADE ----------------
if selected is not None and "WAIT" not in signal:

    st.subheader("🎯 Trade Setup")

    st.write(f"{selected['strike']} {selected['instrument_type']}")
    st.write(f"LTP: {selected['price']}")

    mode = st.radio("Entry Mode", ["Auto", "Manual"])

    if mode == "Auto":
        entry_price = selected["price"]
    else:
        entry_price = st.number_input("Entry Price", value=float(selected["price"]))

    sl = entry_price * 0.88
    t1 = entry_price * 1.2
    t2 = entry_price * 1.4

    c1, c2, c3 = st.columns(3)
    c1.metric("SL", round(sl,2))
    c2.metric("T1", round(t1,2))
    c3.metric("T2", round(t2,2))

    if selected["price"] >= t1:
        st.success("Book Partial + Trail")
    elif selected["price"] < sl:
        st.error("Exit Trade")

# ---------------- OPTION TABLE ----------------
with st.expander("📊 Option Chain"):
    st.dataframe(opt_df[["tradingsymbol","strike","instrument_type","price"]])