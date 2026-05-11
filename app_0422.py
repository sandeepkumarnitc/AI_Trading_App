import streamlit as st
import pandas as pd
import datetime
import requests
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

st.set_page_config(layout="wide", page_title="AI Trading System Pro")

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
if "last_signal" not in st.session_state:
    st.session_state.last_signal = ""

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

price15 = df15["close"].iloc[-1]
ema15 = df15["EMA"].iloc[-1]

# ---------------- VWAP (SAFE FALLBACK) ----------------
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

# ---------------- MARKET TYPE DETECTION ----------------
range_10 = df5["high"].iloc[-10:].max() - df5["low"].iloc[-10:].min()
range_5 = df5["high"].iloc[-5:].max() - df5["low"].iloc[-5:].min()

trend15 = "BULLISH" if price15 > ema15 else "BEARISH"

if range_5 < 0.5 * range_10:
    market_type = "RANGE"
elif abs(price - ema) > 50:
    market_type = "TREND"
else:
    market_type = "EXPANSION"

# ---------------- CORE LOGIC ----------------
df5["vol_ma"] = df5["volume"].rolling(20).mean()
volume_spike = df5["volume"].iloc[-1] > 1.3 * df5["vol_ma"].iloc[-1]

last = df5.iloc[-1]
body = abs(last["close"] - last["open"])
rng = last["high"] - last["low"]
strong = (body / rng) > 0.5 if rng != 0 else False

recent_high = df5["high"].rolling(10).max().iloc[-2]
recent_low = df5["low"].rolling(10).min().iloc[-2]

breakout_up = last["close"] > recent_high
breakout_down = last["close"] < recent_low

# ---------------- NEW LOGIC ----------------

# Pullback
pullback_buy = (
    trend15 == "BULLISH" and
    price > ema and
    last["low"] <= ema and
    last["close"] > last["open"]
)

pullback_sell = (
    trend15 == "BEARISH" and
    price < ema and
    last["high"] >= ema and
    last["close"] < last["open"]
)

# Early breakout
early_buy = breakout_up and trend15 == "BULLISH"
early_sell = breakout_down and trend15 == "BEARISH"

# Afternoon
now = datetime.datetime.now().time()
afternoon = datetime.time(13,30) <= now <= datetime.time(14,30)
compression = range_5 < 0.6 * range_10

expansion_up = breakout_up and volume_spike and strong
expansion_down = breakout_down and volume_spike and strong

# Late
late = now >= datetime.time(14,30)

# ---------------- CHOP DETECTION ----------------

range_5 = df5["high"].iloc[-5:].max() - df5["low"].iloc[-5:].min()
range_10 = df5["high"].iloc[-10:].max() - df5["low"].iloc[-10:].min()

avg_range = (df5["high"] - df5["low"]).rolling(10).mean().iloc[-1]

# Chop = low movement + near EMA/VWAP
chop = (
    range_5 < 0.5 * range_10 and
    abs(price - ema) < avg_range and
    (vwap is None or abs(price - vwap) < avg_range)
)

# ---------------- REVERSAL DETECTION ----------------

reversal_buy = (
    price > ema and
    df5["close"].iloc[-2] < ema and   # was below EMA
    df5["close"].iloc[-1] > ema and   # now above EMA
    strong and
    volume_spike and
    not chop
)

reversal_sell = (
    price < ema and
    df5["close"].iloc[-2] > ema and
    df5["close"].iloc[-1] < ema and
    strong and
    volume_spike and
    not chop
)

# ---------------- SIGNAL ENGINE ----------------
signal = "WAIT"

if reversal_buy:
    signal = "🔄 REVERSAL BUY CALL"

elif reversal_sell:
    signal = "🔄 REVERSAL BUY PUT"

if afternoon and compression:
    if expansion_up:
        signal = "🔥 AFTERNOON CALL"
    elif expansion_down:
        signal = "🔥 AFTERNOON PUT"

elif market_type == "TREND"  and not chop:
    if pullback_buy:
        signal = "🟢 TREND CALL"
    elif pullback_sell:
        signal = "🔴 TREND PUT"

elif market_type == "EXPANSION":
    if early_buy:
        signal = "⚡ EARLY CALL"
    elif early_sell:
        signal = "⚡ EARLY PUT"

elif breakout_up and volume_spike and not chop:
    signal = "BUY CALL"

elif breakout_down and volume_spike  and not chop:
    signal = "BUY PUT"

elif late:
    if expansion_down:
        signal = "🔥 LATE PUT"
    elif expansion_up:
        signal = "🔥 LATE CALL"
    else:
        signal = "NO TRADE"

# ---------------- ALERT ----------------
if signal != st.session_state.last_signal and ("CALL" in signal or "PUT" in signal):

    msg = f"""
🚨 {signal}

Price: {round(price,2)}
EMA: {round(ema,2)}
VWAP: {round(vwap,2) if vwap else "NA"}
Market: {market_type}
Time: {datetime.datetime.now().strftime('%H:%M:%S')}
"""

    st.warning(msg)

    st.markdown(
        """
        <audio autoplay>
        <source src="https://www.soundjay.com/buttons/sounds/beep-07.mp3">
        </audio>
        """,
        unsafe_allow_html=True
    )

    send_telegram(msg)

st.session_state.last_signal = signal

# ---------------- UI ----------------
st.title("📊 AI Trading System PRO")

col1, col2, col3 = st.columns(3)
col1.metric("Price", round(price,2))
col2.metric("EMA", round(ema,2))
col3.metric("VWAP", round(vwap,2) if vwap else "NA")

st.write(f"Market Type: {market_type}")
st.write(f"Trend15: {trend15}")
st.write(f"Volume Spike: {volume_spike} | Strong: {strong}")

st.subheader(f"🚀 Signal: {signal}")