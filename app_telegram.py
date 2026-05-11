import streamlit as st
import pandas as pd
import datetime
import time
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

st.set_page_config(layout="wide", page_title="AI Trading System")

# ---------------- TELEGRAM ----------------
def send_telegram(msg):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": CHAT_ID, "text": msg})
    except:
        pass

# ---------------- AUTO REFRESH ----------------

refresh = st.sidebar.slider("Refresh (sec)", 5, 60, 10)
st_autorefresh(interval=refresh * 1000, key="datarefresh")

# ---------------- SESSION ----------------
if "trades" not in st.session_state:
    st.session_state.trades = []
if "active_trade" not in st.session_state:
    st.session_state.active_trade = None
if "last_signal" not in st.session_state:
    st.session_state.last_signal = ""

# ---------------- HEADER ----------------
st.title("📊 AI Trading System (Pro)")
st.caption("MTF + VWAP + Volume + Afternoon Expansion + Telegram Alerts")

# ---------------- DATA ----------------
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


def get_data(interval):
    data = kite.historical_data(
        256265,  # NIFTY index token
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

# ---------------- CORE LOGIC ----------------
trend15 = "BULLISH" if price15 > ema15 else "BEARISH"

recent_high = df5["high"].rolling(10).max().iloc[-2]
recent_low = df5["low"].rolling(10).min().iloc[-2]

# Chop
range5 = df5["high"].iloc[-5:].max() - df5["low"].iloc[-5:].min()
chop = range5 < 40

# Volume spike
df5["vol_ma"] = df5["volume"].rolling(20).mean()
volume_spike = df5["volume"].iloc[-1] > 1.5 * df5["vol_ma"].iloc[-1]

# Candle strength
last = df5.iloc[-1]
body = abs(last["close"] - last["open"])
rng = last["high"] - last["low"]
strong = (body / rng) > 0.6 if rng != 0 else False

# Breakout
breakout_up = last["close"] > recent_high
breakout_down = last["close"] < recent_low

# Fake breakout
upper_wick = last["high"] - max(last["open"], last["close"])
fake_up = upper_wick > body

# ---------------- AFTERNOON EXPANSION ----------------
now = datetime.datetime.now().time()

afternoon = datetime.time(13,30) <= now <= datetime.time(14,30)

range10 = df5["high"].iloc[-10:].max() - df5["low"].iloc[-10:].min()
compression = range5 < 0.6 * range10

expansion_up = breakout_up and volume_spike and strong
expansion_down = breakout_down and volume_spike and strong

# ---------------- TREND CONTINUATION ----------------

pullback_buy = (
    trend15 == "BULLISH" and
    price > ema and
    last["low"] <= ema and   # pullback to EMA
    last["close"] > last["open"] and  # bullish candle
    not chop
)

pullback_sell = (
    trend15 == "BEARISH" and
    price < ema and
    last["high"] >= ema and
    last["close"] < last["open"] and
    not chop
)

# ---------------- SIGNAL ENGINE ----------------
signal = "WAIT"

if now >= datetime.time(14,30):
    signal = "NO TRADE (EOD)"

elif afternoon and compression:
    if expansion_up:
        signal = "🔥 AFTERNOON CALL"
    elif expansion_down:
        signal = "🔥 AFTERNOON PUT"

elif chop:
    signal = "NO TRADE"

elif trend15 == "BULLISH":
    if breakout_up and volume_spike and not fake_up:
        signal = "BUY CALL"

elif trend15 == "BEARISH":
    if breakout_down and volume_spike:
        signal = "BUY PUT"

elif pullback_buy:
    signal = "🟢 TREND BUY CALL"

elif pullback_sell:
    signal = "🔴 TREND BUY PUT"

# ---------------- ALERT SYSTEM ----------------
if signal != st.session_state.last_signal and ("CALL" in signal or "PUT" in signal):

    alert_msg = f"""
🚨 SIGNAL: {signal}

Price: {round(price,2)}
EMA: {round(ema,2)}
VWAP: {round(vwap,2)}

Volume Spike: {volume_spike}
Time: {datetime.datetime.now().strftime('%H:%M:%S')}
"""

    st.warning(alert_msg)

    # 🔔 SOUND
    st.markdown(
        """
        <audio autoplay>
        <source src="https://www.soundjay.com/buttons/sounds/beep-07.mp3" type="audio/mpeg">
        </audio>
        """,
        unsafe_allow_html=True
    )

    # 📱 TELEGRAM
    send_telegram(alert_msg)

st.session_state.last_signal = signal

# ---------------- UI ----------------
col1, col2, col3 = st.columns(3)
col1.metric("Price", round(price,2))
col2.metric("EMA", round(ema,2))
col3.metric("VWAP", round(vwap,2))

st.write(f"Trend (15m): {trend15}")
st.write(f"Volume Spike: {volume_spike} | Chop: {chop}")
st.subheader(f"🚀 Signal: {signal}")

# ---------------- PAPER TRADE ----------------
if "CALL" in signal or "PUT" in signal:

    entry = st.number_input("Entry Price", value=float(price))
    sl = entry * 0.88
    target = entry * 1.4

    if st.button("Enter Trade"):
        st.session_state.active_trade = {
            "entry": entry,
            "sl": sl,
            "target": target,
            "qty": 75,
            "status": "OPEN"
        }

# ---------------- ACTIVE TRADE ----------------
trade = st.session_state.active_trade

if trade and trade["status"] == "OPEN":

    pnl = (price - trade["entry"]) * trade["qty"]
    st.write(f"PnL: {round(pnl,2)}")

    if price <= trade["sl"]:
        trade["status"] = "SL HIT"
    elif price >= trade["target"]:
        trade["status"] = "TARGET HIT"

    if st.button("Exit Trade"):
        trade["status"] = "MANUAL EXIT"

    if trade["status"] != "OPEN":
        st.session_state.trades.append(trade.copy())
        st.session_state.active_trade = None

# ---------------- HISTORY ----------------
st.subheader("📒 Trade History")

if st.session_state.trades:
    df = pd.DataFrame(st.session_state.trades)
    st.dataframe(df)
else:
    st.info("No trades yet")

st.divider()
st.subheader("🧪 Test Alerts")

if st.button("Send Test Alert"):
    test_msg = f"""
🧪 TEST ALERT

Price: {round(price, 2)}
EMA: {round(ema, 2)}
VWAP: {round(vwap, 2)}

Time: {datetime.datetime.now().strftime('%H:%M:%S')}
"""

    st.success("Test Alert Sent!")

    # 🔔 Sound
    st.markdown(
        """
        <audio autoplay>
        <source src="https://www.soundjay.com/buttons/sounds/beep-07.mp3" type="audio/mpeg">
        </audio>
        """,
        unsafe_allow_html=True
    )

    # 📱 Telegram
    send_telegram(test_msg)