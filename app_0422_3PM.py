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


# ---------------- TRADE STATE ----------------

if "entry_price" not in st.session_state:
    st.session_state.entry_price = None

if "remaining_qty" not in st.session_state:
    st.session_state.remaining_qty = 0


# ---------------- TELEGRAM ----------------
def send_telegram(msg):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": CHAT_ID, "text": msg})

# ---------------- AUTO REFRESH ----------------
refresh = st.sidebar.slider("Refresh (sec)", 5, 60, 10)
st_autorefresh(interval=refresh * 1000, key="refresh")

# ---------------- SESSION ----------------
if "last_signal" not in st.session_state:
    st.session_state.last_signal = ""

if "last_alert_time" not in st.session_state:
    st.session_state.last_alert_time = None

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

# ---------------- VWAP ----------------
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

    data = kite.historical_data(token, from_date, to_date, "5minute")
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

# ---------------- OI TRACKING ----------------

if "last_oi_ce" not in st.session_state:
    st.session_state.last_oi_ce = 0
if "last_oi_pe" not in st.session_state:
    st.session_state.last_oi_pe = 0

def get_option_chain(price):
    df = pd.DataFrame(kite.instruments("NFO"))
    df = df[(df["name"] == "NIFTY") & (df["instrument_type"].isin(["CE","PE"]))]

    expiry = df["expiry"].min()
    df = df[df["expiry"] == expiry]

    base = round(price / 50) * 50
    strikes = [base-200, base-100, base, base+100, base+200]

    df = df[df["strike"].isin(strikes)]

    tokens = df["instrument_token"].tolist()
    quotes = kite.quote(tokens)

    df["oi"] = df["instrument_token"].apply(lambda x: quotes[str(x)]["oi"])
    return df

chain = get_option_chain(price)

ce = chain[chain["instrument_type"]=="CE"]
pe = chain[chain["instrument_type"]=="PE"]

oi_ce = ce["oi"].sum()
oi_pe = pe["oi"].sum()

# Noise filter (fix your 0 issue)
if abs(oi_ce) < 1000:
    oi_ce = st.session_state.last_oi_ce
else:
    st.session_state.last_oi_ce = oi_ce

if abs(oi_pe) < 1000:
    oi_pe = st.session_state.last_oi_pe
else:
    st.session_state.last_oi_pe = oi_pe

# Smart money
if oi_pe > oi_ce:
    smart_money = "BEARISH BUILDUP"
elif oi_ce > oi_pe:
    smart_money = "BULLISH BUILDUP"
else:
    smart_money = "NEUTRAL"

# ---------------- MARKET TYPE ----------------
range_10 = df5["high"].iloc[-10:].max() - df5["low"].iloc[-10:].min()
range_5 = df5["high"].iloc[-5:].max() - df5["low"].iloc[-5:].min()

trend15 = "BULLISH" if price15 > ema15 else "BEARISH"

if range_5 < 0.5 * range_10:
    market_type = "RANGE"
elif abs(price - ema) > 50:
    market_type = "TREND"
else:
    market_type = "EXPANSION"

# ---------------- CORE ----------------
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

# ---------------- LOGIC ----------------
pullback_buy = (
    trend15 == "BULLISH" and
    price > ema and
    last["low"] <= ema * 1.001 and
    last["close"] > ema
)

pullback_sell = trend15 == "BEARISH" and price < ema and last["high"] >= ema*1.001 and last["close"] < last["open"]

early_buy = breakout_up and trend15 == "BULLISH"
early_sell = breakout_down and trend15 == "BEARISH"

now = datetime.datetime.now().time()
afternoon = datetime.time(13,30) <= now <= datetime.time(14,30)
compression = range_5 < 0.6 * range_10

expansion_up = breakout_up and volume_spike and strong
expansion_down = breakout_down and volume_spike and strong

late = now >= datetime.time(14,30)

# ---------------- CHOP ----------------
avg_range = (df5["high"] - df5["low"]).rolling(10).mean().iloc[-1]

chop = (
    range_5 < 0.5 * range_10 and
    abs(price - ema) < avg_range and
    (vwap is None or abs(price - vwap) < avg_range)
)

# ---------------- REVERSAL ----------------
reversal_buy = price > ema and df5["close"].iloc[-2] < ema and strong and volume_spike and not chop
reversal_sell = price < ema and df5["close"].iloc[-2] > ema and strong and volume_spike and not chop


# ---------------- CONFIDENCE SCORE ----------------

score = 0

# 1. Trend alignment (15m)
if trend15 == "BULLISH" and price > ema:
    score += 15
elif trend15 == "BEARISH" and price < ema:
    score += 15

# 2. VWAP alignment (IMPORTANT)
if vwap:
    if price > vwap and trend15 == "BULLISH":
        score += 15
    elif price < vwap and trend15 == "BEARISH":
        score += 15

# 3. Candle strength + volume
if strong:
    score += 10
if volume_spike:
    score += 10

# 4. OI Smart Money
if smart_money == "BULLISH BUILDUP" and trend15 == "BULLISH":
    score += 15
elif smart_money == "BEARISH BUILDUP" and trend15 == "BEARISH":
    score += 15

# 5. Setup strength
if pullback_buy or pullback_sell:
    score += 10

if breakout_up or breakout_down:
    score += 10

if reversal_buy or reversal_sell:
    score += 15

# 6. Chop penalty (VERY IMPORTANT)
if chop:
    score -= 25

# Clamp score
score = max(0, min(100, score))


# ---------------- HARD CHOP FILTER ----------------

hard_chop = (
    chop and
    abs(price - ema) < avg_range and
    (vwap is None or abs(price - vwap) < avg_range)
)

# If strong chop → block everything
if hard_chop:
    signal = "NO TRADE"


# ---------------- SIGNAL ----------------
signal = "WAIT"

if reversal_buy and score > 60:
    signal = "🔄 REVERSAL BUY CALL"
elif reversal_sell and score > 60:
    signal = "🔄 REVERSAL BUY PUT"

elif afternoon and compression:
    if expansion_up:
        signal = "🔥 AFTERNOON CALL"
    elif expansion_down:
        signal = "🔥 AFTERNOON PUT"

elif market_type == "TREND" and not chop:
    if pullback_buy and score > 60:
        signal = "🟢 TREND CALL"
    elif pullback_sell and score > 60:
        signal = "🔴 TREND PUT"

elif market_type == "EXPANSION":
    if early_buy:
        signal = "⚡ EARLY CALL"
    elif early_sell:
        signal = "⚡ EARLY PUT"

elif breakout_up and volume_spike and not chop and score > 65:
    signal = "BUY CALL"

elif breakout_down and volume_spike and not chop and score > 65:
    signal = "BUY PUT"

elif late:
    signal = "NO TRADE"





# ---------------- TRADE MANAGEMENT ----------------

if "trade" not in st.session_state:
    st.session_state.trade = None

# Entry
if st.session_state.trade is None:
    if "CALL" in signal:
        st.session_state.trade = {
            "type": "CALL",
            "entry": price,
            "sl": price - 40,
            "target": price + 80
        }

    elif "PUT" in signal:
        st.session_state.trade = {
            "type": "PUT",
            "entry": price,
            "sl": price + 40,
            "target": price - 80
        }

# Management
if st.session_state.trade:

    trade = st.session_state.trade

    pnl = price - trade["entry"] if trade["type"]=="CALL" else trade["entry"] - price

    exit_reason = None

    if trade["type"]=="CALL":
        if price <= trade["sl"]:
            exit_reason = "SL HIT"
        elif price >= trade["target"]:
            exit_reason = "TARGET HIT"

    elif trade["type"]=="PUT":
        if price >= trade["sl"]:
            exit_reason = "SL HIT"
        elif price <= trade["target"]:
            exit_reason = "TARGET HIT"

    # Exit
    if exit_reason:
        st.success(f"Trade Exit: {exit_reason} | PnL: {round(pnl,2)}")
        st.session_state.trade = None

    # EMA slope filter (block flat market trades)
    ema_slope = df5["EMA"].iloc[-1] - df5["EMA"].iloc[-5]

    if abs(ema_slope) < 5:
        signal = "NO TRADE"



# ---------------- ALERT FIX ----------------
def can_send_alert(signal):
    now = datetime.datetime.now()

    if signal != st.session_state.last_signal:
        return True

    if st.session_state.last_alert_time:
        diff = (now - st.session_state.last_alert_time).seconds
        if diff > 60:
            return True

    return False

if ("CALL" in signal or "PUT" in signal) and can_send_alert(signal):

    msg = f"""
🚨 {signal}

Price: {round(price,2)}
EMA: {round(ema,2)}
VWAP: {round(vwap,2) if vwap else "NA"}
Market: {market_type}
Time: {datetime.datetime.now().strftime('%H:%M:%S')}
"""

    st.warning(msg)

    # sound
    st.markdown("""
    <audio autoplay>
    <source src="https://www.soundjay.com/buttons/sounds/beep-07.mp3">
    </audio>
    """, unsafe_allow_html=True)

    # retry telegram
    for _ in range(3):
        try:
            send_telegram(msg)
            break
        except:
            continue

    st.session_state.last_alert_time = datetime.datetime.now()

st.session_state.last_signal = signal

# Check momentum after entry (last 3 candles)
momentum = df5["close"].iloc[-1] - df5["close"].iloc[-3]

if signal == "SELL" and momentum > -10:
    score -= 10  # weak follow-through

last_range = df5["high"].iloc[-3:].max() - df5["low"].iloc[-3:].min()

if last_range < 20:
    score -= 10  # market slowing down


# ---------------- TRADE MODE ----------------

if score >= 75:
    trade_mode = "STRONG TREND"
elif score >= 60:
    trade_mode = "MODERATE"
else:
    trade_mode = "SCALP"

# ---------------- POSITION SIZE ----------------

if trade_mode == "STRONG TREND":
    qty_multiplier = 1.0   # full position

elif trade_mode == "MODERATE":
    qty_multiplier = 0.7   # reduce size

else:
    qty_multiplier = 0.4   # small size


if signal in ["BUY", "SELL"] and st.session_state.entry_price is None:
    st.session_state.entry_price = price
    st.session_state.remaining_qty = int(130 * qty_multiplier)


# ---------------- PARTIAL BOOKING ----------------

if st.session_state.entry_price is not None:

    pnl = price - st.session_state.entry_price

    # For SELL trades
    if signal == "SELL":
        pnl = st.session_state.entry_price - price

    # MODERATE trades → book early
    if trade_mode == "MODERATE" and pnl > 15 and st.session_state.remaining_qty > 0:
        book_qty = st.session_state.remaining_qty // 2
        st.session_state.remaining_qty -= book_qty

        st.success(f"Partial Booked: {book_qty} units")

    # SCALP trades → quick exit
    elif trade_mode == "SCALP" and pnl > 10:
        st.warning("Quick Exit Suggested (Scalp)")


# ---------------- TRAILING SL ----------------

if st.session_state.entry_price is not None:

    # Move SL to cost after profit
    if pnl > 15:
        trailing_sl = st.session_state.entry_price

    # Lock profits
    if pnl > 30:
        trailing_sl = st.session_state.entry_price + 10 if signal == "BUY" else st.session_state.entry_price - 10

    st.info(f"Trailing SL: {trailing_sl}")



# ---------------- EXIT ----------------

if st.session_state.entry_price is not None:

    if pnl < -15:
        st.error("Stop Loss Hit → Exit Trade")
        st.session_state.entry_price = None

    elif pnl > 50:
        st.success("Target Achieved → Exit Full")
        st.session_state.entry_price = None


# ---------------- UI ----------------
st.title("📊 AI Trading System PRO")

c1,c2,c3 = st.columns(3)
c1.metric("Price", round(price,2))
c2.metric("EMA", round(ema,2))
c3.metric("VWAP", round(vwap,2) if vwap else "NA")

st.write(f"Market Type: {market_type}")
st.write(f"Trend15: {trend15}")
st.write(f"Volume Spike: {volume_spike} | Strong: {strong}")

# ---------------- UI ADDITIONS ----------------

st.subheader("📊 OI Intelligence")
st.write(f"CE OI: {oi_ce}")
st.write(f"PE OI: {oi_pe}")
st.write(f"Smart Money: {smart_money}")

st.subheader("📊 Confidence Score")
st.progress(score / 100)

if score >= 75:
    st.success(f"🔥 Strong Setup ({score})")
elif score >= 60:
    st.warning(f"⚠️ Tradable Setup ({score})")
else:
    st.error(f"❌ Weak Setup ({score})")

st.subheader("📊 Trade Management")

st.write(f"Mode: {trade_mode}")
st.write(f"Entry Price: {st.session_state.entry_price}")
st.write(f"Remaining Qty: {st.session_state.remaining_qty}")
st.write(f"Live PnL: {round(pnl,2) if st.session_state.entry_price else 0}")

if st.session_state.trade:
    trade = st.session_state.trade
    st.subheader("💼 Active Trade")
    st.write(trade)

st.subheader(f"🚀 Signal: {signal}")