import streamlit as st
import pandas as pd
import datetime
import requests
import time
from kiteconnect import KiteConnect
from streamlit_autorefresh import st_autorefresh

# ---------------- CONFIG ----------------
API_KEY = "35clx8i5b5na7iz9"
BOT_TOKEN = "8554043412:AAEgT9adN-l24lklPWlVlxLtOaz9Gsx1gsM"
CHAT_ID = "8114054476"

with open("access_token.txt", "r") as f:
    ACCESS_TOKEN = f.read().strip()

kite = KiteConnect(api_key=API_KEY)
kite.set_access_token(ACCESS_TOKEN)

st.set_page_config(layout="wide", page_title="AI Trading System PRO MAX")

# ---------------- TELEGRAM ----------------
def send_telegram(msg):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": CHAT_ID, "text": msg})
    except:
        pass

# ---------------- AUTO REFRESH ----------------
refresh = st.sidebar.slider("Refresh (sec)", 5, 60, 10)
st_autorefresh(interval=refresh * 1000, key="refresh")

# ---------------- SESSION ----------------
if "position" not in st.session_state:
    st.session_state.position = None

if "entry_price" not in st.session_state:
    st.session_state.entry_price = None

if "sl" not in st.session_state:
    st.session_state.sl = None

if "target" not in st.session_state:
    st.session_state.target = None

if "bars_in_trade" not in st.session_state:
    st.session_state.bars_in_trade = 0

if "partial_booked" not in st.session_state:
    st.session_state.partial_booked = False

if "last_signal" not in st.session_state:
    st.session_state.last_signal = ""

if "oi_buffer" not in st.session_state:
    st.session_state.oi_buffer = {}

if "oi_trend" not in st.session_state:
    st.session_state.oi_trend = []

# ---------------- DATA ----------------
def get_data(interval):
    data = kite.historical_data(
        256265,
        datetime.datetime.now() - datetime.timedelta(days=5),
        datetime.datetime.now(),
        interval
    )
    df = pd.DataFrame(data)
    df["date"] = pd.to_datetime(df["date"])
    df["EMA"] = df["close"].ewm(span=44).mean()
    return df

df5 = get_data("5minute")
df15 = get_data("15minute")

price = df5["close"].iloc[-1]
ema = df5["EMA"].iloc[-1]

# ---------------- VWAP (FUTURES STYLE) ----------------
@st.cache_data
def get_fut_token():
    instruments = kite.instruments("NFO")
    df = pd.DataFrame(instruments)

    fut = df[
        (df["name"] == "NIFTY") &
        (df["instrument_type"] == "FUT")
    ]

    expiry = fut["expiry"].min()
    return int(fut[fut["expiry"] == expiry].iloc[0]["instrument_token"])

def get_fut_data(token):
    data = kite.historical_data(
        instrument_token=token,
        from_date=datetime.datetime.now() - datetime.timedelta(days=2),
        to_date=datetime.datetime.now(),
        interval="5minute"
    )

    df = pd.DataFrame(data)
    df["date"] = pd.to_datetime(df["date"])
    return df

fut_token = get_fut_token()
df_fut = get_fut_data(fut_token)

# Only today's data
today = df_fut["date"].dt.date.iloc[-1]
df_today = df_fut[df_fut["date"].dt.date == today].copy()

# Remove zero volume
df_today = df_today[df_today["volume"] > 0]

# VWAP calc
df_today["cum_vol"] = df_today["volume"].cumsum()
df_today["cum_val"] = (df_today["close"] * df_today["volume"]).cumsum()
df_today["VWAP"] = df_today["cum_val"] / df_today["cum_vol"]

# Final value
if not df_today.empty:
    vwap = df_today["VWAP"].iloc[-1]
else:
    vwap = None

# ---------------- STRUCTURE ----------------
recent = df5.tail(5)

hh = all(recent["high"].diff().dropna() > 0)
hl = all(recent["low"].diff().dropna() > 0)

lh = all(recent["high"].diff().dropna() < 0)
ll = all(recent["low"].diff().dropna() < 0)

if hh and hl:
    structure = "UP"
elif lh and ll:
    structure = "DOWN"
else:
    structure = "SIDEWAYS"

# ---------------- PHASE ----------------
df5["body"] = abs(df5["close"] - df5["open"])
df5["range"] = df5["high"] - df5["low"]
df5["body_ratio"] = df5["body"] / df5["range"]

df5["tr"] = df5["high"] - df5["low"]
df5["atr"] = df5["tr"].rolling(14).mean()
df5["move"] = abs(df5["close"] - df5["close"].shift())
df5["vol_ratio"] = df5["move"] / df5["atr"]

latest = df5.iloc[-1]

if latest["vol_ratio"] > 1.2 and latest["body_ratio"] > 0.6:
    phase = "IMPULSE"
elif latest["vol_ratio"] < 0.8 and latest["body_ratio"] < 0.5 and structure != "SIDEWAYS":
    phase = "DRIFT"
else:
    phase = "CHOP"

# ---------------- OPTION CHAIN ----------------
@st.cache_data
def get_option_instruments():
    df = pd.DataFrame(kite.instruments("NFO"))
    return df[(df["name"] == "NIFTY") & (df["instrument_type"].isin(["CE","PE"]))]

opt_df = get_option_instruments()
expiry = opt_df["expiry"].min()
opt_df = opt_df[opt_df["expiry"] == expiry]

def get_strikes(price):
    base = round(price / 50) * 50
    return [base - 200, base - 100, base, base + 100, base + 200]

chain = opt_df[opt_df["strike"].isin(get_strikes(price))]

tokens = chain["instrument_token"].tolist()
quote = kite.quote(tokens)

chain["ltp"] = chain["instrument_token"].apply(lambda x: quote[str(x)]["last_price"])
chain["oi"] = chain["instrument_token"].apply(lambda x: quote[str(x)]["oi"])

ce = chain[chain["instrument_type"]=="CE"][["strike","ltp","oi"]]
pe = chain[chain["instrument_type"]=="PE"][["strike","ltp","oi"]]

option_chain = pd.merge(ce, pe, on="strike", suffixes=("_CE","_PE"))

# ---------------- OI BUFFER (IMPROVED) ----------------
timestamp = int(time.time())

for _, row in option_chain.iterrows():
    strike = row["strike"]

    st.session_state.oi_buffer.setdefault(strike, []).append({
        "time": timestamp,
        "ce": row["oi_CE"],
        "pe": row["oi_PE"]
    })

    # increased buffer size
    if len(st.session_state.oi_buffer[strike]) > 15:
        st.session_state.oi_buffer[strike].pop(0)

# ---------------- ΔOI ----------------
oi_change_ce = 0
oi_change_pe = 0

for strike, history in st.session_state.oi_buffer.items():
    if len(history) >= 2:
        first = history[0]
        last = history[-1]

        oi_change_ce += (last["ce"] - first["ce"])
        oi_change_pe += (last["pe"] - first["pe"])

# ---------------- OI TREND STABILITY ----------------
oi_trend_signal = 0

if oi_change_ce > 0:
    oi_trend_signal = 1
elif oi_change_pe > 0:
    oi_trend_signal = -1

st.session_state.oi_trend.append(oi_trend_signal)

if len(st.session_state.oi_trend) > 5:
    st.session_state.oi_trend.pop(0)

bull_count = st.session_state.oi_trend.count(1)
bear_count = st.session_state.oi_trend.count(-1)

# ---------------- SMART MONEY ----------------
price_change = df5["close"].iloc[-1] - df5["close"].iloc[-2]

threshold = 50000

if abs(oi_change_ce) < threshold and abs(oi_change_pe) < threshold:
    smart_money = "NO PARTICIPATION"

elif bull_count >= 3:
    smart_money = "BULLISH BUILDUP"

elif bear_count >= 3:
    smart_money = "BEARISH BUILDUP"

elif oi_change_pe < 0 and price_change > 0:
    smart_money = "SHORT COVERING"

elif oi_change_ce < 0 and price_change < 0:
    smart_money = "LONG UNWINDING"

else:
    smart_money = "NEUTRAL"

# ---------------- TRAP DETECTION ----------------
recent_low = df5["low"].rolling(5).min().iloc[-2]
recent_high = df5["high"].rolling(5).max().iloc[-2]

curr = df5.iloc[-1]

trap = None

if curr["low"] < recent_low and curr["close"] > recent_low:
    trap = "BEAR TRAP"

elif curr["high"] > recent_high and curr["close"] < recent_high:
    trap = "BULL TRAP"


# ---------------- BREAKOUT CONFIRMATION ----------------

recent_low = df5["low"].rolling(5).min().iloc[-2]
recent_high = df5["high"].rolling(5).max().iloc[-2]

curr = df5.iloc[-1]

body = abs(curr["close"] - curr["open"])
range_ = curr["high"] - curr["low"]

body_ratio = body / range_ if range_ != 0 else 0

# Bearish confirmation candle
bearish_break_confirm = (
    curr["close"] < recent_low and
    body_ratio > 0.6 and
    curr["close"] < curr["open"]
)

# Bullish confirmation candle
bullish_break_confirm = (
    curr["close"] > recent_high and
    body_ratio > 0.6 and
    curr["close"] > curr["open"]
)


# If no confirmation candle → no trade
if not bearish_break_confirm and not bullish_break_confirm:
    signal = "NO TRADE (No Break Confirmation)"

# ---------------- CONFIDENCE SCORE ----------------
score = 0

# Trend strength (EMA alignment)
if structure == "DOWN" and price < ema:
    score += 20
elif structure == "UP" and price > ema:
    score += 20

# Structure clarity
if structure in ["UP", "DOWN"]:
    score += 15

# Phase strength
if phase == "IMPULSE":
    score += 20
elif phase == "DRIFT":
    score += 10

# OI strength
oi_strength = abs(oi_change_ce) + abs(oi_change_pe)

if oi_strength > 200000:
    score += 20
elif oi_strength > 100000:
    score += 10

# Smart money alignment
if smart_money in ["BULLISH BUILDUP", "BEARISH BUILDUP"]:
    score += 15

# Trap filter
if trap is None:
    score += 10
else:
    score -= 20  # strong penalty

# Cap score
score = max(0, min(100, score))


# ---------------- UPDATED SIGNAL ----------------
signal = "NO TRADE"
entry = sl = target = strike = None

if smart_money == "NO PARTICIPATION":
    signal = "NO TRADE (No OI Activity)"

elif trap is not None:
    signal = f"NO TRADE ({trap})"

# 🔴 BEARISH
elif structure == "DOWN" and price < ema and phase in ["DRIFT", "IMPULSE"]:
    if smart_money == "BEARISH BUILDUP" and bearish_break_confirm:
        if score >= 70:
            signal = "BUY PE"
            entry = price
            sl = curr["high"]
            target = entry - 2 * (sl - entry)
            strike = round(price / 50) * 50
        else:
            signal = f"WAIT (Low Confidence {score})"
    else:
        signal = "WAIT (Weak Bearish)"

# 🟢 BULLISH
elif structure == "UP" and price > ema and phase in ["DRIFT", "IMPULSE"]:
    if smart_money == "BULLISH BUILDUP" and bullish_break_confirm   :
        if score >= 70:
            signal = "BUY CE"
            entry = price
            sl = curr["low"]
            target = entry + 2 * (entry - sl)
            strike = round(price / 50) * 50
        else:
            signal = f"WAIT (Low Confidence {score})"
    else:
        signal = "WAIT (Weak Bullish)"

if signal in ["BUY CE", "BUY PE"]:
    st.session_state.position = signal
    st.session_state.entry_price = entry
    st.session_state.sl = sl
    st.session_state.target = target
    st.session_state.bars_in_trade = 0
    st.session_state.partial_booked = False


exit_signal = None

if st.session_state.position:

    st.session_state.bars_in_trade += 1

    entry_price = st.session_state.entry_price
    sl = st.session_state.sl
    target = st.session_state.target

    risk = abs(entry_price - sl)
    one_r = risk

    # ---------------- PARTIAL BOOKING ----------------
    if not st.session_state.partial_booked:
        if st.session_state.position == "BUY CE" and price >= entry_price + one_r:
            exit_signal = "PARTIAL BOOK (50%)"
            st.session_state.partial_booked = True
            st.session_state.sl = entry_price  # move SL to cost

        elif st.session_state.position == "BUY PE" and price <= entry_price - one_r:
            exit_signal = "PARTIAL BOOK (50%)"
            st.session_state.partial_booked = True
            st.session_state.sl = entry_price

    # ---------------- TRAILING SL ----------------
    if st.session_state.partial_booked:
        if st.session_state.position == "BUY CE":
            st.session_state.sl = max(st.session_state.sl, curr["low"])

        elif st.session_state.position == "BUY PE":
            st.session_state.sl = min(st.session_state.sl, curr["high"])

    # ---------------- STOP LOSS HIT ----------------
    if st.session_state.position == "BUY CE" and price <= st.session_state.sl:
        exit_signal = "EXIT SL HIT"
        st.session_state.position = None

    elif st.session_state.position == "BUY PE" and price >= st.session_state.sl:
        exit_signal = "EXIT SL HIT"
        st.session_state.position = None

    # ---------------- TARGET HIT ----------------
    if st.session_state.position == "BUY CE" and price >= target:
        exit_signal = "EXIT TARGET HIT"
        st.session_state.position = None

    elif st.session_state.position == "BUY PE" and price <= target:
        exit_signal = "EXIT TARGET HIT"
        st.session_state.position = None

    # ---------------- TIME EXIT ----------------
    if st.session_state.bars_in_trade >= 8:
        exit_signal = "EXIT TIME (No Momentum)"
        st.session_state.position = None


exit_signal = None

if st.session_state.position:

    st.session_state.bars_in_trade += 1

    entry_price = st.session_state.entry_price
    sl = st.session_state.sl
    target = st.session_state.target

    risk = abs(entry_price - sl)
    one_r = risk

    # ---------------- PARTIAL BOOKING ----------------
    if not st.session_state.partial_booked:
        if st.session_state.position == "BUY CE" and price >= entry_price + one_r:
            exit_signal = "PARTIAL BOOK (50%)"
            st.session_state.partial_booked = True
            st.session_state.sl = entry_price  # move SL to cost

        elif st.session_state.position == "BUY PE" and price <= entry_price - one_r:
            exit_signal = "PARTIAL BOOK (50%)"
            st.session_state.partial_booked = True
            st.session_state.sl = entry_price

    # ---------------- TRAILING SL ----------------
    if st.session_state.partial_booked:
        if st.session_state.position == "BUY CE":
            st.session_state.sl = max(st.session_state.sl, curr["low"])

        elif st.session_state.position == "BUY PE":
            st.session_state.sl = min(st.session_state.sl, curr["high"])

    # ---------------- STOP LOSS HIT ----------------
    if st.session_state.position == "BUY CE" and price <= st.session_state.sl:
        exit_signal = "EXIT SL HIT"
        st.session_state.position = None

    elif st.session_state.position == "BUY PE" and price >= st.session_state.sl:
        exit_signal = "EXIT SL HIT"
        st.session_state.position = None

    # ---------------- TARGET HIT ----------------
    if st.session_state.position == "BUY CE" and price >= target:
        exit_signal = "EXIT TARGET HIT"
        st.session_state.position = None

    elif st.session_state.position == "BUY PE" and price <= target:
        exit_signal = "EXIT TARGET HIT"
        st.session_state.position = None

    # ---------------- TIME EXIT ----------------
    if st.session_state.bars_in_trade >= 8:
        exit_signal = "EXIT TIME (No Momentum)"
        st.session_state.position = None


# ---------------- UI ----------------
st.title("📊 AI Trading System PRO MAX")

col1, col2, col3 = st.columns(3)
col1.metric("Price", round(price,2))
col2.metric("EMA", round(ema,2))
col3.metric("VWAP", round(vwap,2))

st.write(f"Structure: {structure}")
st.write(f"Phase: {phase}")
st.write(f"Smart Money: {smart_money}")
st.write(f"Trap: {trap}")

st.write(f"Breakdown Confirmed: {bearish_break_confirm}")
st.write(f"Breakout Confirmed: {bullish_break_confirm}")

st.subheader(f"🚀 Signal: {signal}")

st.subheader("📊 Confidence Score")

st.progress(score / 100)

if score >= 80:
    st.success(f"🔥 Strong Setup ({score})")
elif score >= 60:
    st.warning(f"⚠️ Moderate Setup ({score})")
else:
    st.error(f"❌ Weak Setup ({score})")

st.subheader("📊 OI Intelligence")
st.write(f"ΔOI CE: {oi_change_ce}")
st.write(f"ΔOI PE: {oi_change_pe}")

st.subheader("📉 Trade Management")

if st.session_state.position:
    st.write(f"Position: {st.session_state.position}")
    st.write(f"Entry: {st.session_state.entry_price}")
    st.write(f"SL: {st.session_state.sl}")
    st.write(f"Target: {st.session_state.target}")
    st.write(f"Bars in Trade: {st.session_state.bars_in_trade}")

if exit_signal:
    st.error(f"🚨 {exit_signal}")

st.subheader("📊 Option Chain")
st.dataframe(option_chain)