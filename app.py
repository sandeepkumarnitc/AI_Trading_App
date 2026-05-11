# ================= IMPORTS =================
import streamlit as st
import pandas as pd
import datetime
import requests
from kiteconnect import KiteConnect
from streamlit_autorefresh import st_autorefresh
import json
import os

# ---------------- CONFIG ----------------
API_KEY = "35clx8i5b5na7iz9"
BOT_TOKEN = "8554043412:AAEgT9adN-l24lklPWlVlxLtOaz9Gsx1gsM"
CHAT_ID = "8114054476"

with open("access_token.txt", "r") as f:
    ACCESS_TOKEN = f.read().strip()

kite = KiteConnect(api_key=API_KEY)
kite.set_access_token(ACCESS_TOKEN)

st.set_page_config(layout="wide", page_title="AI Trading System PRO MAX")
st.markdown("""
<style>
/* Make everything bigger for mobile */
html, body, [class*="css"]  {
    font-size: 18px;
}

/* Big signal box */
.signal-box {
    font-size: 28px;
    font-weight: bold;
    text-align: center;
    padding: 16px;
    border-radius: 12px;
    margin-bottom: 10px;
}

/* Green / Red themes */
.buy { background-color: #0f5132; color: white; }
.sell { background-color: #842029; color: white; }
.wait { background-color: #41464b; color: white; }

/* Metric cards */
.metric {
    font-size: 20px;
    padding: 10px;
}
</style>
""", unsafe_allow_html=True)


entry_quality = 100

def show_signal(signal):
    if "CALL" in signal:
        cls = "signal-box buy"
    elif "PUT" in signal:
        cls = "signal-box sell"
    else:
        cls = "signal-box wait"

    st.markdown(f'<div class="{cls}">{signal}</div>', unsafe_allow_html=True)

# ----------------------Trade Log File---------------------------------
TRADE_LOG_FILE = "trade_logs.json"


def load_trade_logs():
    try:
        with open(TRADE_LOG_FILE, "r") as f:
            return json.load(f)
    except:
        return []


def save_trade_logs(logs):
    with open(TRADE_LOG_FILE, "w") as f:
        json.dump(logs, f, default=str)


if "trade" in st.session_state and isinstance(st.session_state.trade, dict):
    if "strike" not in st.session_state.trade:
        st.session_state.trade = None

# ---------------- SESSION ----------------
for key, val in {
    "trade": None,
    "last_signal": "",
    "last_alert_time": None,
    "last_oi_ce": 0,
    "last_oi_pe": 0
}.items():
    if key not in st.session_state:
        st.session_state[key] = val

if "trade_logs" not in st.session_state:
    st.session_state.trade_logs = load_trade_logs()

if "prev_oi_ce" not in st.session_state:
    st.session_state.prev_oi_ce = None

if "prev_oi_pe" not in st.session_state:
    st.session_state.prev_oi_pe = None

if "last_trade_time" not in st.session_state:
    st.session_state.last_trade_time = None

if "last_stage" not in st.session_state:
    st.session_state.last_stage = None


# ================= EXECUTABLE SIGNALS =================

EXECUTABLE_SIGNALS = [

    # CALLS
    "🚀 BUY CALL (CONFIRMED BREAKOUT)",
    "🎯 BUY CALL (VWAP BOUNCE)",
    "⚡ BUY CALL (EMA BOUNCE)",
    "🔥 BUY CALL (BEAR TRAP REVERSAL)",
    "🔥 BUY CALL (RETEST ENTRY)",
    "🚀 STRONG BUY CALL - MOMENTUM",
    "🚀 TREND REVERSAL CONFIRMED - BUY CALL",

    # PUTS
    "🚀 BUY PUT (CONFIRMED BREAKDOWN)",
    "🚀 BUY PUT (BREAKDOWN ENTRY)",
    "🚀 BUY PUT (STRONG BREAKDOWN)",
    "🎯 BUY PUT (RETEST ENTRY)",
    "🔥 BUY PUT (EMA REJECTION)",
    "🔥 BUY PUT (VWAP REJECTION)",
    "🔥 BUY PUT (VWAP REJECTION CONFIRMED)",
    "🔥 BUY PUT (BULL TRAP REVERSAL)",
    "🔥 BUY PUT (BULL TRAP CONFIRMATION)",
    "🚀 TREND REVERSAL CONFIRMED - BUY PUT"
]

# ---------------- OI FILE STORAGE ----------------
OI_FILE = "oi_data.json"


def load_oi_file():
    if os.path.exists(OI_FILE):
        try:
            with open(OI_FILE, "r") as f:
                return json.load(f)
        except:
            return []
    return []


def save_oi_file(data):
    with open(OI_FILE, "w") as f:
        json.dump(data, f, default=str)


# ----------OI Trend-------------------------
if "oi_history" not in st.session_state:
    st.session_state.oi_history = load_oi_file()


# ---------------- TELEGRAM ----------------
def send_telegram(msg):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        res = requests.post(url, data={"chat_id": CHAT_ID, "text": msg})
        print(res.text)  # debug
    except Exception as e:
        print("Telegram Error:", e)


# ---------------- AUTO REFRESH ----------------
refresh = st.sidebar.slider("Refresh (sec)", 5, 60, 10)
st_autorefresh(interval=refresh * 1000, key="refresh")


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
df1h = get_data("60minute")
price1h = df1h["close"].iloc[-1]
ema1h = df1h["EMA"].iloc[-1]
trend1h = "BULLISH" if price1h > ema1h else "BEARISH"

price = df5["close"].iloc[-1]
ema = df5["EMA"].iloc[-1]

price15 = df15["close"].iloc[-1]
ema15 = df15["EMA"].iloc[-1]

trend15 = "BULLISH" if price15 > ema15 else "BEARISH"

# ---------------- MULTI TF TREND ALIGNMENT ----------------

trend_alignment = 0

if trend1h == trend15:
    trend_alignment += 1

if trend15 == ("BULLISH" if price > ema else "BEARISH"):
    trend_alignment += 1

# Strong alignment
if trend1h == trend15 == ("BULLISH" if price > ema else "BEARISH"):
    trend_alignment = 3

# ---------------- SPOT VWAP (MATCH TRADINGVIEW) ----------------

# Use SAME spot dataframe as strategy engine
df_vwap = df5.copy()

# Keep only today's session
today = df_vwap["date"].dt.date.iloc[-1]

df_vwap = df_vwap[
    df_vwap["date"].dt.date == today
].copy()

# TradingView-style Typical Price
df_vwap["tp"] = (
    df_vwap["high"] +
    df_vwap["low"] +
    df_vwap["close"]
) / 3

# IMPORTANT:
# Nifty spot volume is unreliable/zero,
# so use futures volume mapping later

# Temporary placeholder
df_vwap["temp_index"] = range(len(df_vwap))

# Futures volume mapping
inst = pd.DataFrame(kite.instruments("NFO"))

fut = inst[
    (inst["name"] == "NIFTY") &
    (inst["instrument_type"] == "FUT")
]

fut = fut.sort_values("expiry")

symbols = fut.head(3)["instrument_token"].tolist()

quotes = kite.quote(symbols)

fut["volume_check"] = fut["instrument_token"].apply(
    lambda x: quotes[str(x)]["volume"]
    if str(x) in quotes else 0
)

current_fut = fut.sort_values(
    "volume_check",
    ascending=False
).iloc[0]

token = int(current_fut["instrument_token"])

# Fetch futures ONLY for volume
df_fut_vol = pd.DataFrame(
    kite.historical_data(
        token,
        datetime.datetime.now() - datetime.timedelta(days=1),
        datetime.datetime.now(),
        "5minute"
    )
)

df_fut_vol["date"] = pd.to_datetime(df_fut_vol["date"])

# Merge futures volume into spot candles
df_vwap = pd.merge_asof(
    df_vwap.sort_values("date"),
    df_fut_vol[["date", "volume"]].sort_values("date"),
    on="date",
    direction="nearest",
    suffixes=("_spot", "_fut")
)

# Use FUTURES volume
df_vwap["fut_volume"] = df_vwap["volume_fut"]

# Safety fill
df_vwap["fut_volume"].fillna(method="ffill", inplace=True)

# VWAP using spot price + futures volume
df_vwap["pv"] = df_vwap["tp"] * df_vwap["fut_volume"]

df_vwap["cum_pv"] = df_vwap["pv"].cumsum()
df_vwap["cum_vol"] = df_vwap["fut_volume"].cumsum()

df_vwap["VWAP"] = (
    df_vwap["cum_pv"] / df_vwap["cum_vol"]
)

vwap = round(float(df_vwap["VWAP"].iloc[-1]), 2)

if pd.isna(vwap):
    vwap = price

# Safe VWAP slope calculation
if len(df_vwap) >= 5:
    vwap_slope = df_vwap["VWAP"].iloc[-1] - df_vwap["VWAP"].iloc[-5]
elif len(df_vwap) >= 2:
    vwap_slope = df_vwap["VWAP"].iloc[-1] - df_vwap["VWAP"].iloc[0]
else:
    vwap_slope = 0



# ---------------- SELECT ACTIVE FUTURES CONTRACT ----------------

fut = fut.sort_values("expiry")

symbols = fut.head(3)["instrument_token"].tolist()

quotes = kite.quote(symbols)

fut["volume_check"] = fut["instrument_token"].apply(
    lambda x: quotes[str(x)]["volume"]
    if str(x) in quotes else 0
)

# Pick highest volume contract
current_fut = fut.sort_values(
    "volume_check",
    ascending=False
).iloc[0]

token = int(current_fut["instrument_token"])

print("Using FUT:", current_fut["tradingsymbol"])

df_fut = pd.DataFrame(
    kite.historical_data(
        token,
        datetime.datetime.now() - datetime.timedelta(days=2),
        datetime.datetime.now(),
        "5minute"
    )
)

df_fut["date"] = pd.to_datetime(df_fut["date"])

# ================= FUTURES VOLUME MAPPING =================
df_fut = df_fut.sort_values("date")

# Merge nearest timestamps
df5 = pd.merge_asof(
    df5.sort_values("date"),
    df_fut[["date", "volume"]].sort_values("date"),
    on="date",
    direction="nearest",
    suffixes=("", "_fut")
)

# Rename for clarity
df5["fut_volume"] = df5["volume_fut"]

# Clean NaN if any
df5["fut_volume"].fillna(method="ffill", inplace=True)
# 🚨 FIX LOW / INVALID VOLUME
if df5["fut_volume"].iloc[-1] < 1000:
    df5["fut_volume"].iloc[-1] = df5["fut_volume"].iloc[-2]


#============Set Signal==============================
trade_signal = False
def set_signal(new_signal, strength):
    global signal, signal_strength

    if "signal_strength" not in globals():
        signal_strength = 0

    HIGH_PRIORITY = [
        "🎯 BUY PUT (RETEST ENTRY)",
        "🚀 BUY PUT (BREAKDOWN ENTRY)",
        "🔥 BUY PUT (BULL TRAP REVERSAL)",
        "🔥 BUY PUT (EMA REJECTION)",
        "🔥 BUY PUT (VWAP REJECTION)",            # ✅ ADD
        "🔥 BUY PUT (BULL TRAP CONFIRMATION)",    # ✅ ADD
        "🚀 STRONG BUY CALL - MOMENTUM",
        "🚀 BUY CALL (CONFIRMED BREAKOUT)",
        "💎 PERFECT PUT ENTRY"
    ]

    # ================= SIGNAL LOCK (CRITICAL FIX) =================

    LOCK_SIGNALS = [
        "⚠️ LOW VOLUME - NO TRADE",
        "⚠️ POST MOVE PAUSE - WAIT",
        "⚠️ TOO LATE TO SELL - WAIT PULLBACK",
        "⚠️ EXTENDED MOVE - WAIT PULLBACK"
    ]

    if signal in LOCK_SIGNALS:
        pass  # 🔥 DO NOT OVERRIDE THESE

    # 🚨 HARD LOCK: never override strong signals
    if signal in HIGH_PRIORITY and strength < signal_strength:
        return

    if strength >= signal_strength:
        signal = new_signal
        signal_strength = strength



# ================= TRAP + BREAKOUT INTELLIGENCE =================
def is_breakdown_setup(df, support, vwap):
    last = df.iloc[-1]

    near_support = last["close"] <= support * 1.002
    below_vwap = last["close"] < vwap

    return near_support and below_vwap


def detect_levels(df):
    recent = df.tail(20)

    # EXCLUDE last 2 candles (very important)
    resistance = recent["high"].iloc[:-2].max()
    support = recent["low"].iloc[:-2].min()

    if abs(resistance - support) < 25:
        resistance = resistance + 15
        support = support - 15

    return resistance, support


# ================= RANGE DETECTION =================

def detect_range(df):
    recent = df.tail(20)

    high = recent["high"].max()
    low = recent["low"].min()

    range_size = high - low

    # Range if tight + low momentum
    is_range = (
        range_size < 120
        and abs(recent["close"].iloc[-1] - recent["close"].iloc[-5]) < 40
        and df["fut_volume"].iloc[-1] < df["vol_ma"].iloc[-1]
    )

    return is_range, high, low

#================= Range Breakout Prep =============================

def range_breakout_prep(
        price,
        resistance,
        support,
        vwap,
        ema,
        futures_volume,
        volume_ma
):

    # ================= DYNAMIC RANGE WIDTH =================
    range_width = resistance - support

    tight_range = (
        range_width < 180
    )

    # ================= SMART DISTANCE =================
    resistance_distance = resistance - price

    near_breakout = (
        resistance_distance < 70
    )

    # ================= IMPROVED BULLISH STRUCTURE =================
    bullish_structure = (
        price > ema
        and price > (vwap - 15)
    )

    # ================= HEALTHY PARTICIPATION =================
    healthy_volume = (
        futures_volume > (volume_ma * 0.45)
    )

    # ================= COMPRESSION DETECTION =================
    compression = (
        resistance_distance < 50
        and price > support + (range_width * 0.55)
    )

    # ================= EARLY TREND CONTINUATION =================
    bullish_pressure = (
        price > ema
        and resistance_distance < 90
        and futures_volume > (volume_ma * 0.35)
    )

    return (
        (
            tight_range
            and near_breakout
            and bullish_structure
            and healthy_volume
        )
        or compression
        or bullish_pressure
    )

def is_bull_trap(df, resistance):
    if len(df) < 3:
        return False

    prev = df.iloc[-2]
    last = df.iloc[-1]

    breakout = prev["close"] > resistance * 0.999

    upper_wick = prev["high"] - prev["close"]
    body = abs(prev["close"] - prev["open"])

    weak_breakout = upper_wick > body
    no_follow = last["close"] < prev["close"]

    # 🚨 NEW STRICT CONDITION (CRITICAL FIX)
    below_vwap = last["close"] < vwap
    below_ema = last["close"] < ema

    return breakout and weak_breakout and no_follow and below_vwap and below_ema


def is_bear_trap(df, support):
    if len(df) < 3:
        return False

    prev = df.iloc[-2]
    last = df.iloc[-1]

    breakdown = prev["close"] < support * 1.001

    lower_wick = prev["close"] - prev["low"]
    body = abs(prev["open"] - prev["close"])

    weak_breakdown = lower_wick > body
    reversal = last["close"] > support

    return breakdown and weak_breakdown and reversal


def breakout_score(df, vwap, ema):
    score = 0

    last = df.iloc[-1]

    body = abs(last.close - last.open)
    rng = last.high - last.low

    # Candle strength
    if rng > 0:
        ratio = body / rng
        if ratio > 0.7:
            score += 30
        elif ratio > 0.5:
            score += 20
        else:
            score += 10

    # Volume
    avg_vol = df["fut_volume"].rolling(20).mean().iloc[-1]

    if last["fut_volume"] > 1.5 * avg_vol:
        score += 20
    elif last["fut_volume"] > avg_vol:
        score += 10

    # VWAP + EMA
    if last.close > vwap:
        score += 20
    if last.close > ema:
        score += 10

    return score


# ================= TRAP STRENGTH =================

def trap_strength(df, vwap):
    if len(df) < 3:
        return 0

    prev = df.iloc[-2]
    last = df.iloc[-1]

    strength = 0

    recent_move = abs(
        df["close"].iloc[-1] -
        df["close"].iloc[-5]
    )

    normal_bearish_trend = (
            price < ema
            and price < vwap
            and smart_money == "BEARISH BUILDUP"
            and recent_move < 40
    )

    normal_bullish_trend = (
            price > ema
            and price > vwap
            and smart_money == "BULLISH BUILDUP"
            and recent_move < 40
    )

    # Wick strength (rejection)
    upper_wick = prev["high"] - max(prev["close"], prev["open"])
    lower_wick = min(prev["close"], prev["open"]) - prev["low"]
    body = abs(prev["close"] - prev["open"])

    if upper_wick > body:
        strength += 20
    if lower_wick > body:
        strength += 20

    # Opposite move confirmation
    if last["close"] < prev["close"]:
        strength += 20
    elif last["close"] > prev["close"]:
        strength += 20

    # VWAP shift (VERY IMPORTANT)
    if last["close"] < vwap:
        strength += 20
    elif last["close"] > vwap:
        strength += 20

    # Volume expansion
    vol = df["fut_volume"].iloc[-1]
    vol_ma = df["vol_ma"].iloc[-1]

    if vol > 1.5 * vol_ma:
        strength += 20
    elif vol > vol_ma:
        strength += 10

    if normal_bearish_trend or normal_bullish_trend:
        strength = min(strength, 40)

    return strength


# ================= REJECTION DETECTION =================

def is_resistance_rejection(df, resistance):
    if len(df) < 3:
        return False

    last = df.iloc[-1]
    prev = df.iloc[-2]

    # Price near resistance
    near_res = last["high"] >= resistance * 0.998

    # Upper wick condition (selling pressure)
    upper_wick = last["high"] - max(last["close"], last["open"])
    body = abs(last["close"] - last["open"])

    wick_rejection = upper_wick > body

    # No breakout continuation
    failed_break = last["close"] < resistance

    return near_res and wick_rejection and failed_break


# ================= BREAKOUT CONFIRMATION =================

def is_breakout_confirmed(df, resistance):
    if len(df) < 3:
        return False

    prev = df.iloc[-2]
    last = df.iloc[-1]

    # Step 1: breakout happened
    breakout = prev["close"] > resistance * 0.999

    # Step 2: strong candle (body > wick)
    body = abs(prev["close"] - prev["open"])
    upper_wick = prev["high"] - prev["close"]

    strong = body > upper_wick

    # Step 3: follow-through
    follow = last["close"] > prev["close"]

    return breakout and strong and follow


# ---------------- OI ----------------
def get_oi_trend():
    hist = st.session_state.oi_history

    if len(hist) < 3:
        return "INSUFFICIENT"

    # 🔥 FIX: ensure numeric
    ce_values = [int(x["ce"]) for x in hist if "ce" in x]
    pe_values = [int(x["pe"]) for x in hist if "pe" in x]

    if len(ce_values) < 2 or len(pe_values) < 2:
        return "INSUFFICIENT"

    ce_trend = ce_values[-1] - ce_values[0]
    pe_trend = pe_values[-1] - pe_values[0]

    if abs(ce_trend) < 50000 and abs(pe_trend) < 50000:
        return "WEAK"

    if pe_trend > ce_trend:
        return "STRONG BEARISH"
    elif ce_trend > pe_trend:
        return "STRONG BULLISH"

    return "NEUTRAL"


def get_option_chain(price):
    df = inst[(inst["name"] == "NIFTY") & (inst["instrument_type"].isin(["CE", "PE"]))]
    expiry = df["expiry"].min()
    df = df[df["expiry"] == expiry]

    base = round(price / 50) * 50
    strikes = [base - 200, base - 100, base, base + 100, base + 200]
    df = df[df["strike"].isin(strikes)]

    tokens = df["instrument_token"].tolist()
    quotes = kite.quote(tokens)

    df["oi"] = df["instrument_token"].apply(lambda x: quotes[str(x)]["oi"])
    return df


chain = get_option_chain(price)

oi_ce = chain[chain.instrument_type == "CE"]["oi"].sum()
oi_pe = chain[chain.instrument_type == "PE"]["oi"].sum()

st.session_state.oi_history.append({
    "time": datetime.datetime.now(),
    "ce": int(oi_ce),
    "pe": int(oi_pe)
})

for item in st.session_state.oi_history:
    item["ce"] = int(item["ce"])
    item["pe"] = int(item["pe"])

save_oi_file(st.session_state.oi_history)

oi_trend = get_oi_trend()

# ================= LOW VOLUME OI FILTER =================

# Ensure vol_ma exists before usage
if "vol_ma" not in df5.columns:
    df5["vol_ma"] = (
        df5["fut_volume"]
        .rolling(20)
        .mean()
        .fillna(method="bfill")
    )

current_vol = float(df5["fut_volume"].iloc[-1])
avg_vol = float(df5["vol_ma"].iloc[-1])

# Safety fallback
if avg_vol <= 0 or pd.isna(avg_vol):
    avg_vol = current_vol

# Ignore noisy OI during dead volume
if current_vol < avg_vol * 0.45:

    if oi_trend in [
        "STRONG BULLISH",
        "STRONG BEARISH"
    ]:
        oi_trend = "WEAK"

# Keep only last 10 readings
st.session_state.oi_history = st.session_state.oi_history[-10:]
save_oi_file(st.session_state.oi_history)

# OI stability fix
if abs(oi_ce) < 1000:
    oi_ce = st.session_state.last_oi_ce
else:
    st.session_state.last_oi_ce = oi_ce

if abs(oi_pe) < 1000:
    oi_pe = st.session_state.last_oi_pe
else:
    st.session_state.last_oi_pe = oi_pe

if st.session_state.prev_oi_ce is None:
    oi_ce_change = 0
    oi_pe_change = 0
else:
    oi_ce_change = oi_ce - st.session_state.prev_oi_ce
    oi_pe_change = oi_pe - st.session_state.prev_oi_pe

# Update previous values
st.session_state.prev_oi_ce = oi_ce
st.session_state.prev_oi_pe = oi_pe

# Ratio
oi_ratio = (oi_pe / oi_ce) if oi_ce != 0 else 0

if price < vwap and oi_ce > oi_pe:
    oi_bias = "BEARISH"

elif price > vwap and oi_pe > oi_ce:
    oi_bias = "BULLISH"

else:
    oi_bias = "NEUTRAL"


# ================= POSITION SIZING =================

def get_position_size(score, breakout_strength, volume_spike):
    # ❌ No trade zone
    if score < 50 and "TRAP REVERSAL" not in signal:
        return 0

    # 🚀 Strong setup
    if score >= 80 and breakout_strength > 70 and volume_spike:
        return 3

    # 🟢 Good setup
    elif score >= 65:
        return 2

    # 🟡 Moderate setup
    else:
        return 1


# ---------------- STRIKE SELECTION ----------------
def select_strike(price, signal):
    base = round(price / 50) * 50
    if "CALL" in signal:
        return base if "EARLY" in signal else base - 50
    if "PUT" in signal:
        return base if "EARLY" in signal else base + 50
    return base


def get_option_price(strike, opt_type):
    df = inst[(inst["name"] == "NIFTY") &
              (inst["strike"] == strike) &
              (inst["instrument_type"] == opt_type)]
    expiry = df["expiry"].min()
    token = int(df[df["expiry"] == expiry].iloc[0]["instrument_token"])
    return kite.quote([token])[str(token)]["last_price"]


# ---------------- CONFIDENCE ----------------
df5["vol_ma"] = df5["fut_volume"].rolling(20).mean()
volume_spike = df5["fut_volume"].iloc[-1] > 1.3 * df5["vol_ma"].iloc[-1]

last = df5.iloc[-1]
body = abs(last.close - last.open)
rng = last.high - last.low
strong = (body / rng) > 0.5 if rng else False

score = 0

if vwap_slope > 5:
    score += 5

elif vwap_slope < -5:
    score -= 5

if trend15 == "BULLISH" and price > ema: score += 15
if trend15 == "BEARISH" and price < ema: score += 15

if price > vwap and trend15 == "BULLISH": score += 15
if price < vwap and trend15 == "BEARISH": score += 15

if strong: score += 10
if volume_spike: score += 10

# OI Trend (NEW - powerful)
if oi_trend == "STRONG BULLISH" and trend15 == "BULLISH":
    score += 20

elif oi_trend == "STRONG BEARISH" and trend15 == "BEARISH":
    score += 20

elif oi_trend == "WEAK":
    score -= 5   # ❗ reduce penalty

    # 🚀 If price structure is strong, don't penalize much
    if price < vwap and price < ema:
        score += 5

if trend1h == trend15:
    score += 10

if trend1h == trend15 == ("BULLISH" if price > ema else "BEARISH"):
    score += 10

# filters
ema_slope = df5["EMA"].iloc[-1] - df5["EMA"].iloc[-5]

# ================= EMA TREND DIRECTION (NEW) =================

ema_trending_down = ema_slope < -5
ema_trending_up = ema_slope > 5

# Extra structure intelligence
ema_flat = abs(ema_slope) <= 5

# Bearish drift detection
bearish_drift = (
    price < ema
    and price < vwap
    and ema_trending_down
    and df5["close"].iloc[-1] < df5["close"].iloc[-3]
)

# Bullish drift detection
bullish_drift = (
    price > ema
    and price > vwap
    and ema_trending_up
    and df5["close"].iloc[-1] > df5["close"].iloc[-3]
)

# Score adjustments
if bearish_drift:
    score += 10

if bullish_drift:
    score += 10

# Flat EMA = weaker trend environment
if ema_flat:
    score -= 5

price_move = abs(price - df5["close"].iloc[-10])
if price_move > 80:
    entry_quality -= 30

#score = max(0, min(100, score))

# ================= NEW INTELLIGENCE LAYER =================
signal = "NO TRADE"
signal_strength = 0
resistance, support = detect_levels(df5)

bull_trap = is_bull_trap(df5, resistance)
bear_trap = is_bear_trap(df5, support)

is_range, range_high, range_low = detect_range(df5)

# ================= RANGE BREAKOUT PREP LOGIC =================

range_breakout_ready = range_breakout_prep(
    price,
    resistance,
    support,
    vwap,
    ema,
    df5["fut_volume"].iloc[-1],
    df5["vol_ma"].iloc[-1]
)

if is_range:

    # 🚀 bullish compression inside range
    if (
        range_breakout_ready
        and price > ema
        and price > support + ((resistance - support) * 0.5)
    ):

        set_signal(
            "🟡 BREAKOUT BUILDUP - WATCH RESISTANCE",
            78
        )

    # ⚠️ only true dead range
    elif (
        abs(price - vwap) < 20
        and df5["fut_volume"].iloc[-1] <
            df5["vol_ma"].iloc[-1] * 0.5
    ):

        set_signal(
            "📦 RANGE DETECTED - WAIT FOR BREAKOUT",
            60
        )


# ================= SMART MONEY (FIXED REAL PRICE ACTION LOGIC) =================

price_change_5 = price - df5["close"].iloc[-5]
volume_trend = df5["fut_volume"].iloc[-1] - df5["fut_volume"].iloc[-5]

# ================= STRONG SELL PRESSURE =================
strong_sell_pressure = (
    price < vwap
    and price < ema
    and df5["close"].iloc[-1] < df5["close"].iloc[-2]
    and df5["fut_volume"].iloc[-1] > df5["vol_ma"].iloc[-1]
)

# ================= STRONG BUY PRESSURE =================
strong_buy_pressure = (
    price > vwap
    and price > ema
    and df5["close"].iloc[-1] > df5["close"].iloc[-2]
    and df5["fut_volume"].iloc[-1] > df5["vol_ma"].iloc[-1]
)

# ================= DISTRIBUTION =================
distribution = (
    abs(price_change_5) < 20
    and volume_trend < 0
    and price < resistance
    and price > support
)

# ================= ACCUMULATION =================
accumulation = (
    abs(price_change_5) < 20
    and volume_trend > 0
    and price > vwap
)

# ================= FINAL SMART MONEY =================
if strong_sell_pressure:

    smart_money = "BEARISH BUILDUP"

elif strong_buy_pressure:

    smart_money = "BULLISH BUILDUP"

elif distribution:

    smart_money = "DISTRIBUTION"

elif accumulation:

    smart_money = "ACCUMULATION"

else:

    # Fallback from OI structure
    if oi_ce > oi_pe:
        smart_money = "BEARISH BUILDUP"
    else:
        smart_money = "BULLISH BUILDUP"


# 🚨 TRAP INVALIDATION (CRITICAL FIX)
if price > vwap and price > ema:
    bull_trap = False

if price < vwap and price < ema:
    bear_trap = False


trap_score = trap_strength(df5, vwap)

# 🔥 FIX: cap trap score to avoid false inflation
trap_score = min(trap_score, 80)

# 🔥 FIX: reduce trap bias in clean breakdown
if price < support and price < vwap and price < ema:
    trap_score -= 20
    trap_score = max(trap_score, 0)


low_volume = df5["fut_volume"].iloc[-1] < 0.3 * df5["vol_ma"].iloc[-1]

if low_volume:
    if (
        smart_money == "BEARISH BUILDUP"
        and price < ema
        and price < support
    ):
        set_signal(
            "⚠️ WEAK BREAKDOWN - LOW CONFIDENCE PUTS",
            75
        )
    else:
        set_signal(
            "⚠️ LOW VOLUME - NO TRADE",
            100
        )


# ================= SCORE NORMALIZATION FIX (CRITICAL) =================

# 🚀 VOLUME BOOST (missing in your system)
if df5["fut_volume"].iloc[-1] > 1.5 * df5["vol_ma"].iloc[-1]:
    score += 10


# ⚠️ TRAP PENALTY (FIXED - previously too aggressive)
if trap_score >= 90:
    score -= 15   # confirmed trap
elif trap_score >= 80:
    score -= 5    # warning only
elif trap_score >= 65:
    score -= 3

rejection = is_resistance_rejection(df5, resistance)

if rejection and not volume_spike:
    rejection = False

rejection_confirmed = rejection and df5.iloc[-1]["close"] < df5.iloc[-2]["low"]


# ================= RANGE BREAKOUT FILTER =================

range_breakout = (
    is_range
    and price > range_high
    and df5["fut_volume"].iloc[-1] > df5["vol_ma"].iloc[-1]
)

range_breakdown = (
    is_range
    and price < range_low
    and df5["fut_volume"].iloc[-1] > df5["vol_ma"].iloc[-1]
)


breakout_confirmed = is_breakout_confirmed(df5, resistance)

if breakout_confirmed:
    resistance = resistance  # keep old resistance for few candles

# ================= SMART BREAKOUT STRUCTURE FIX =================

if breakout_confirmed and price > resistance:

    old_resistance = resistance

    # recent valid swing low after breakout
    recent_support = (
        df5["low"]
        .iloc[-8:-1]
        .min()
    )

    # use safer support
    support = min(
        old_resistance,
        recent_support
    )

    # NEVER allow support above current price
    support = min(
        support,
        price - 5
    )

    # dynamic new resistance
    recent_high = (
        df5["high"]
        .tail(10)
        .max()
    )

    # ensure proper gap
    if recent_high <= support:
        recent_high = support + 40

    resistance = recent_high

    # freeze structure
    st.session_state.frozen_support = support
    st.session_state.frozen_resistance = resistance

if breakout_confirmed and price > vwap and price > ema:
    score += 20

breakout_strength = breakout_score(df5, vwap, ema)
breakdown_setup = is_breakdown_setup(df5, support, vwap)
breakdown_confirmed = (
        price < support
        and df5["close"].iloc[-1] < df5["close"].iloc[-2]
        and df5["fut_volume"].iloc[-1] > df5["vol_ma"].iloc[-1]
        and price < vwap
        and price < ema
)

# ================= PRICE ACTION OVERRIDE =================

if (
    price > vwap
    and price > ema
    and breakout_strength >= 55
    and df5["fut_volume"].iloc[-1] >
        df5["vol_ma"].iloc[-1]
):

    smart_money = "BULLISH BUILDUP"

    if oi_trend == "STRONG BEARISH":
        oi_bias = "SHORT COVERING RALLY"

if smart_money == "BULLISH BUILDUP" and trend15 == "BULLISH": score += 15
if smart_money == "BEARISH BUILDUP" and trend15 == "BEARISH": score += 15

# ================= LEVEL FREEZE SYSTEM =================

if "frozen_support" not in st.session_state:
    st.session_state.frozen_support = support

if "frozen_resistance" not in st.session_state:
    st.session_state.frozen_resistance = resistance

# Freeze support after real breakdown
if (
    price < support
    and breakout_strength >= 35
    and df5["fut_volume"].iloc[-1] >
        df5["vol_ma"].iloc[-1]
):
    st.session_state.frozen_support = support

# Freeze resistance after real breakout
# Freeze breakout support correctly
if breakout_confirmed and price > resistance:

    st.session_state.frozen_support = support

    st.session_state.frozen_resistance = max(
        df5["high"].tail(10)
    )

# ================= SAFE FROZEN LEVELS =================

support = min(
    st.session_state.frozen_support,
    price - 5
)

resistance = max(
    st.session_state.frozen_resistance,
    price + 5
)


# ================= STRUCTURE SHIFT DETECTION (CRITICAL FIX) =================

# Detect if breakdown already happened recently
recent_breakdown = df5["low"].iloc[-5:].min() < support

# Price reclaiming structure (VERY IMPORTANT)
structure_reclaim = (
    recent_breakdown
    and price > support
    and df5["close"].iloc[-1] > df5["close"].iloc[-2]
)

# 🚨 FAILED BREAKDOWN FILTER (BLOCK WRONG PUT SIGNALS)
# ================= FAILED BREAKDOWN DETECTION (FIXED) =================

recent_breakdown = (
    df5["close"].iloc[-5:].min() < support
)

strong_reclaim = (
    price > support + 15
    and price > vwap
    and price > ema
)

failed_breakdown = (
    recent_breakdown
    and strong_reclaim
    and breakout_strength < 50
)

# 🚀 Ignore failed breakdown during bullish expansion
if (
    price > vwap
    and price > ema
    and breakout_strength >= 55
    and df5["fut_volume"].iloc[-1] >
        df5["vol_ma"].iloc[-1]
):
    failed_breakdown = False


if failed_breakdown:
    set_signal("⚠️ FAILED BREAKDOWN - AVOID PUT", 98)
    trade_signal = False
    score -= 20

# 🚀 STRUCTURE RECLAIM BULLISH BIAS (OPTIONAL BOOST)
if structure_reclaim and price > vwap:
    score += 10
    set_signal("🔄 STRUCTURE RECLAIM - WATCH CALL", 85)

# ================= FAKE BREAKOUT DETECTION =================

fake_breakout = (
    breakout_confirmed
    and price < resistance   # back inside range
    and df5["close"].iloc[-1] < df5["close"].iloc[-2]
    and df5["fut_volume"].iloc[-1] < df5["vol_ma"].iloc[-1]
)

fake_breakdown = (
    breakdown_confirmed
    and price > support
    and df5["close"].iloc[-1] > df5["close"].iloc[-2]
    and df5["fut_volume"].iloc[-1] < df5["vol_ma"].iloc[-1]
)

# ================= TREND CONTINUATION =================
trend_continuation_bear = (
    price < vwap
    and price < ema
    and trend15 == "BEARISH"
    and df5["close"].iloc[-1] < df5["close"].iloc[-3]
)

if trend_continuation_bear:
    if df5["fut_volume"].iloc[-1] < df5["vol_ma"].iloc[-1]:
        set_signal("⚠️ WEAK CONTINUATION - HOLD EXISTING PUTS", 85)
    else:
        score += 10
        set_signal("🔴 BEARISH CONTINUATION - HOLD / SELL ON RISE", 88)


late_move = (
    price < support
    and abs(price - df5["close"].iloc[-10]) > 80
)

if late_move:
    set_signal("⚠️ MOVE DONE - WAIT PULLBACK", 85)


if low_volume and breakout_strength < 40:
    score = min(score, 60)

# ================= POST MOVE PAUSE (UPGRADED LOGIC) =================

# Recent candle compression after expansion
recent_range = (
    df5["high"].tail(3).max() -
    df5["low"].tail(3).min()
)

avg_range = (
    (df5["high"] - df5["low"])
    .rolling(20)
    .mean()
    .iloc[-1]
)

# Detect if strong move already happened
recent_expansion = (
    abs(price - df5["close"].iloc[-8]) > 60
)

# Compression after move
range_compression = (
    recent_range < avg_range * 0.7
)

# Market pausing near EMA after move
ema_pause = (
    abs(price - ema) < 20
)

post_move_pause = (
    recent_expansion
    and range_compression
    and ema_pause
    and df5["fut_volume"].iloc[-1] < df5["vol_ma"].iloc[-1]
    and breakout_strength < 40
)

if post_move_pause:
    score = min(score, 50)
    set_signal("⚠️ POST MOVE PAUSE - WAIT", 90)


# ================= CONTINUATION vs DRIFT FIX =================

continuation_active = (
    price < support
    and price < vwap
    and price < ema
    and df5["fut_volume"].iloc[-1] > df5["vol_ma"].iloc[-1]
)

post_breakdown_drift = (
    price < support
    and price < vwap
    and price < ema
    and df5["fut_volume"].iloc[-1] < df5["vol_ma"].iloc[-1]
)

if continuation_active:
    set_signal("⚠️ BEARISH CONTINUATION - WAIT FOR PULLBACK", 75)

elif post_breakdown_drift:
    set_signal("⚠️ POST BREAKDOWN DRIFT - WAIT", 90)
    score -= 10


# ================= EMA SLOPE CONTEXT ENGINE (NEW) =================

# Bearish continuation with EMA rollover
if (
    bearish_drift
    and price < support
):

    if df5["fut_volume"].iloc[-1] > df5["vol_ma"].iloc[-1]:
        set_signal(
            "🔴 EMA ROLLOVER BREAKDOWN - SELLERS ACTIVE",
            88
        )
    else:
        set_signal(
            "⚠️ BEARISH DRIFT - WEAK MOMENTUM",
            82
        )

# Bullish continuation with EMA expansion
elif (
    bullish_drift
    and price > resistance
):

    if df5["fut_volume"].iloc[-1] > df5["vol_ma"].iloc[-1]:
        set_signal(
            "🟢 EMA EXPANSION - BUYERS ACTIVE",
            88
        )
    else:
        set_signal(
            "⚠️ BULLISH DRIFT - WEAK MOMENTUM",
            82
        )


# ================= POST BREAKDOWN CONTINUATION =================
post_breakdown = (
    price < support
    and df5["close"].iloc[-1] < support
    and df5["close"].iloc[-2] < support
    and price < vwap
    and price < ema
)

if post_breakdown and not continuation_active:
    set_signal("🔴 POST BREAKDOWN - NO FRESH ENTRY", 80)

# 🚀 POST BREAKOUT CONTINUATION (NEW LOGIC)
post_breakout_hold = (
        price > resistance
        and df5["close"].iloc[-1] > resistance
        and df5["close"].iloc[-2] > resistance
        and df5["fut_volume"].iloc[-1] > df5["vol_ma"].iloc[-1] * 0.8
)

if post_breakout_hold and price > ema:
    score += 15
    set_signal("⚡ POST BREAKOUT HOLD - WATCH CALL", 65)

if (
        breakout_strength > 50 and
        df5["fut_volume"].iloc[-1] > df5["vol_ma"].iloc[-1] and
        smart_money == "BULLISH BUILDUP"
):
    trap_score -= 40  # remove false trap bias

if breakout_confirmed and trap_score < 50:
    bull_trap = False
    bear_trap = False

if breakout_confirmed and breakout_strength < 50:
    breakout_confirmed = False

# 🚨 WEAK BREAKOUT FILTER (VERY IMPORTANT)
if breakout_confirmed and price < vwap:
    breakout_confirmed = False
    score -= 25
    set_signal("⚠️ WEAK BREAKOUT (BELOW VWAP)", 70)

if breakout_confirmed and smart_money == "BEARISH BUILDUP":
    trap_score += 25

# 🚨 SMART MONEY CONFLICT (ENHANCED)
if oi_trend == "STRONG BULLISH" and smart_money == "BEARISH BUILDUP":
    score -= 15
    trap_score += 20

    if abs(price - resistance) < 25:
        set_signal("🚨 LIKELY BULL TRAP ZONE", 80)

# Case 2: Strong bearish OI but bullish buildup → pullback / short covering
elif oi_trend == "STRONG BEARISH" and smart_money == "BULLISH BUILDUP":
    score -= 10   # lighter penalty

if oi_trend == "STRONG BULLISH" and price < vwap:
    oi_bias = "SHORT COVERING (NOT BULLISH)"

elif oi_trend == "STRONG BEARISH" and price > vwap:
    oi_bias = "LONG UNWINDING"

# ================= EXHAUSTION vs LATE MOVE FIX =================

bearish_exhaustion = (
    price < vwap
    and price < ema
    and df5["fut_volume"].iloc[-1] < df5["vol_ma"].iloc[-1]
    and breakout_strength < 30
    and abs(price - df5["close"].iloc[-5]) < 40
    and abs(price - support) > 25
)

too_late_sell = (
    price < vwap
    and price < ema
    and abs(price - vwap) > 70
    and df5["fut_volume"].iloc[-1] >= df5["vol_ma"].iloc[-1]  # still strong trend
)

if bearish_exhaustion:
    set_signal("⚠️ BEARISH MOVE EXHAUSTED - WAIT / REVERSAL ZONE", 85)
    score -= 5

elif too_late_sell:
    set_signal("⚠️ TOO LATE TO SELL - WAIT PULLBACK", 90)
    score -= 10


# 🧯 EXHAUSTION DETECTION (IMPROVED)
exhaustion = (
    price < vwap and
    breakout_strength < 30 and
    df5["fut_volume"].iloc[-1] < df5["vol_ma"].iloc[-1] and
    score < 60 and
    df5["close"].iloc[-1] < df5["close"].iloc[-2]  # 🔥 momentum shift
)

if exhaustion:
    set_signal("⚠️ MOMENTUM LOST - WAIT / PULLBACK", 75)
    entry_quality -= 20


# =========================
# AUTO BREAKDOWN ENTRY
# =========================
early_breakdown_entry = (
    price <= support * 1.002
    and price < vwap
    and price < ema
    and df5["fut_volume"].iloc[-1] > df5["vol_ma"].iloc[-1] * 0.8
    and df5["close"].iloc[-1] < df5["close"].iloc[-2]
)

recent_break_low = df5["low"].iloc[-6:-1].min()

fresh_breakdown = (
    recent_break_low >= support * 0.998
)

strong_volume_breakdown = (
    df5["fut_volume"].iloc[-1] >
    df5["vol_ma"].iloc[-1] * 1.2
)

momentum_expanding = (
    df5["close"].iloc[-1] <
    df5["close"].iloc[-2]
)

not_extended_move = (
    abs(price - support) < 45
)

breakdown_entry = (
    price < support
    and fresh_breakdown
    and not_extended_move
    and df5["close"].iloc[-2] >= support * 0.998
    and df5["close"].iloc[-1] < support
    and strong_volume_breakdown
    and momentum_expanding
    and price < vwap
    and price < ema
    and trap_score < 70
    and smart_money == "BEARISH BUILDUP"
    and oi_bias == "BEARISH"
)

if early_breakdown_entry:
    set_signal("⚡ EARLY PUT (BREAKDOWN)", 70)
    trade_signal = True

# =========================
# PULLBACK ENTRY (NEW LOGIC)
# =========================

# 🟢 VWAP BOUNCE (BEST SETUP)
vwap_bounce = (
    price > vwap and
    df5["low"].iloc[-1] <= vwap and
    df5["close"].iloc[-1] > df5["open"].iloc[-1] and  # bullish candle
    df5["fut_volume"].iloc[-1] > df5["vol_ma"].iloc[-1] and
    trend15 == "BULLISH" and
    price > ema
)

# 🟡 EMA BOUNCE (TREND CONTINUATION)
ema_bounce = (
    price > ema and
    df5["low"].iloc[-1] <= ema and
    df5["close"].iloc[-1] > df5["open"].iloc[-1] and
    trend15 == "BULLISH" and
    price > vwap
)

# Strength boost
if vwap_bounce:
    score += 20

elif ema_bounce:
    score += 10


# ================= BREAKOUT ANTICIPATION =================

# Near resistance zone
near_resistance = abs(price - resistance) < 20

# Bullish pressure build-up
bullish_pressure = (
        price > vwap and
        df5["fut_volume"].iloc[-1] > df5["vol_ma"].iloc[-1] and
        oi_bias == "BULLISH"
)

# Bearish pressure near support
near_support = abs(price - support) < 20

bearish_pressure = (
        price < vwap and
        df5["fut_volume"].iloc[-1] > df5["vol_ma"].iloc[-1] and
        oi_bias == "BEARISH"
)

# Anticipation flags
breakout_anticipation = near_resistance and bullish_pressure and not breakout_confirmed
breakdown_anticipation = near_support and bearish_pressure and not breakout_confirmed

# ================= BREAKOUT PRESSURE (NEW - SMART EARLY SIGNAL) =================


# Detect compression near resistance with rising intent
breakout_pressure = (
        price > vwap and
        price > ema and
        (resistance - price) < 30 and
        df5["fut_volume"].iloc[-1] > 0.3 * df5["vol_ma"].iloc[-1]
)

# 🚨 WEAK BREAKOUT ZONE (NO VOLUME CONFIRMATION)
if (
        price < resistance  # ✅ FIX ADDED
        and price < vwap
        and abs(price - resistance) < 20
        and df5["fut_volume"].iloc[-1] < df5["vol_ma"].iloc[-1]
):
    score -= 20
    set_signal("⚠️ WEAK BREAKOUT ZONE - AVOID", 80)

# =========================
# BREAKDOWN RETEST ENTRY
# =========================
retest_breakdown = (
        price < support
        and df5["low"].iloc[-2] < support  # breakdown happened
        and df5["close"].iloc[-1] < support
        and df5["high"].iloc[-1] <= support + 10  # weak pullback
        and price < vwap
        and price < ema
        and df5["fut_volume"].iloc[-1] > df5["vol_ma"].iloc[-1]
)

recent_breakdown = df5["close"].iloc[-5:].min() < support

# ================= EMA REJECTION ENTRY (NEW - CRITICAL FIX) =================

ema_rejection = (
    abs(price - ema) < 20
    and price < ema
    and price < vwap
    and df5["close"].iloc[-1] < df5["open"].iloc[-1]  # red candle
    and df5["high"].iloc[-1] >= ema  # touched EMA
    and df5["fut_volume"].iloc[-1] > 0.8 * df5["vol_ma"].iloc[-1]
    and trend15 == "BEARISH"
)

if ema_rejection:
    set_signal("🔥 BUY PUT (EMA REJECTION)", 92)
    trade_signal = True

fresh_retest = (
    df5["high"].iloc[-3:].max() > support + 40  # meaningful pullback
)

retest_breakdown = retest_breakdown and fresh_retest

trend_continuation = (
        price > ema and
        price > vwap and
        trend15 == "BULLISH" and
        df5["close"].iloc[-1] > df5["close"].iloc[-3]
)

# ================= BREAKDOWN PRESSURE (UPGRADED - CRITICAL FIX) =================

breakdown_pressure = (
    price <= support * 1.005   # near support
    and price < vwap
    and price < ema
    and df5["fut_volume"].iloc[-1] > 0.8 * df5["vol_ma"].iloc[-1]
)

# 🔥 STRONG VERSION (early entry trigger)
breakdown_pressure_strong = (
    price <= support * 1.002
    and price < vwap
    and price < ema
    and df5["fut_volume"].iloc[-1] > df5["vol_ma"].iloc[-1]
    and df5["close"].iloc[-1] < df5["close"].iloc[-2]
)

# ================= PRE-BREAKDOWN AWARENESS =================

pre_breakdown_zone = (
    price <= support * 1.002
    and price < vwap
    and price < ema
    and df5["fut_volume"].iloc[-1] < df5["vol_ma"].iloc[-1]
    and df5["close"].iloc[-1] <= df5["close"].iloc[-2]
)

if pre_breakdown_zone and not breakdown_pressure_strong:
    set_signal("👁 PRE-BREAKDOWN - WATCH CLOSELY", 70)

# Bull trap → go PUT
bull_trap_reversal = (
    bull_trap and
    trap_score >= 70 and
    price < vwap and
    df5["close"].iloc[-1] < df5["close"].iloc[-2] and
    df5["fut_volume"].iloc[-1] >= df5["vol_ma"].iloc[-1] * 0.8
)

# ================= HIGH QUALITY BREAKDOWN ENTRY =================

strong_breakdown = (
    breakdown_entry
    and df5["fut_volume"].iloc[-1] > df5["vol_ma"].iloc[-1]
    and df5["close"].iloc[-1] < df5["low"].iloc[-2]
)

if strong_breakdown:
    set_signal("🚀 BUY PUT (STRONG BREAKDOWN)", 95)

# Boost confidence if trend supports
if bull_trap_reversal and trend15 == "BEARISH":
    score += 10

bear_trap_reversal = (
    bear_trap and
    trap_score >= 70 and
    price > vwap and
    df5["close"].iloc[-1] > df5["close"].iloc[-2] and
    df5["fut_volume"].iloc[-1] >= df5["vol_ma"].iloc[-1] * 0.8
)

# Boost confidence if trend supports
if bear_trap_reversal and trend15 == "BULLISH":
    score += 10

if bear_trap and price < vwap:
    bear_trap = False

# ================= VWAP REJECTION ENTRY (NEW) =================

vwap_rejection = (
    price < vwap
    and df5["high"].iloc[-1] >= vwap
    and df5["close"].iloc[-1] < df5["open"].iloc[-1]
    and df5["fut_volume"].iloc[-1] > 0.8 * df5["vol_ma"].iloc[-1]
    and trend15 == "BEARISH"
)

# 🚀 NEW: CONFIRMATION (VERY IMPORTANT)
vwap_rejection_confirmed = (
    vwap_rejection and
    df5["close"].iloc[-1] < df5["low"].iloc[-2]
)

if vwap_rejection_confirmed:
    score += 15
    set_signal("🔥 BUY PUT (VWAP REJECTION CONFIRMED)", 96)
    trade_signal = True

elif vwap_rejection:
    set_signal("🔥 BUY PUT (VWAP REJECTION)", 93)
    trade_signal = True



# ================= SELL ON RISE ZONE (NEW EDGE) =================

sell_on_rise_zone = (
    price < vwap and
    price < ema and
    abs(price - vwap) < 40 and   # near VWAP pullback
    df5["fut_volume"].iloc[-1] < df5["vol_ma"].iloc[-1]  # weak bounce
)

if sell_on_rise_zone:
    score += 10
    set_signal("🎯 SELL ON RISE ZONE (VWAP PULLBACK)", 90)


# ================= SCALP SCORE BOOST (NEW FIX) =================

if "WEAK BULLISH PULLBACK" in signal:
    score = max(score, 45)   # don't let it go too low

if "COUNTER TREND" in signal:
    score = max(score, 40)

# ---------------- SIGNAL (PRIORITY ENGINE) ----------------
# 🚨 BLOCK FAKE BREAKOUT SIGNALS
if fake_breakout:
    set_signal("❌ FAKE BREAKOUT - AVOID CALL", 95)
    trade_signal = False
    score -= 20

if fake_breakdown:
    set_signal("❌ FAKE BREAKDOWN - AVOID PUT", 95)
    trade_signal = False
    score -= 20
# 🚨 FAKE STRENGTH FILTER (CRITICAL)
if (
        score >= 70 and
        price < vwap and
        df5["fut_volume"].iloc[-1] < df5["vol_ma"].iloc[-1] * 0.5
        and breakout_strength < 30
        and trend15 != "BEARISH"
):
    set_signal("⚠️ WEAK STRUCTURE - FADE BIAS", 85)

near_support = abs(price - support) / support < 0.002  # within 0.2%

breakout_retest = (
        breakout_confirmed
        and price > vwap
        and ema < price < resistance  # small pullback
        and score >= 70
)

resistance_buffer = 0.0015 * resistance  # ~0.15%
near_resistance = abs(price - resistance) < resistance_buffer


bull_trap_confirmed = (
    price > resistance
    and df5["close"].iloc[-1] < df5["open"].iloc[-1]  # red candle
    and df5["high"].iloc[-1] > resistance
)


# 🚫 1. TRAPS (HIGHEST PRIORITY)
if bull_trap and trap_score >= 60 and price < vwap:
    set_signal("❌ BULL TRAP - AVOID CALL", 95)

if bull_trap_confirmed and price < vwap and price < ema:
    set_signal("🔥 BUY PUT (BULL TRAP CONFIRMED)", 95)
    trade_signal = True

elif bear_trap and trap_score >= 60 and price > vwap:
    set_signal("❌ BEAR TRAP - AVOID PUT", 95)

elif bull_trap_reversal:
    set_signal("🔥 BUY PUT (BULL TRAP REVERSAL)", 95)
    trade_signal = True

# 🔥 BEAR TRAP REVERSAL
elif bear_trap_reversal:
    set_signal("🔥 BUY CALL (BEAR TRAP REVERSAL)", 95)
    trade_signal = True

# 🚀 2. DIRECT ENTRIES
elif vwap_bounce and score >= 60:
    set_signal("🎯 BUY CALL (VWAP BOUNCE)", 85)
    trade_signal = True

elif ema_bounce and score >= 55:
    set_signal("⚡ BUY CALL (EMA BOUNCE)", 75)
    trade_signal = True

elif breakdown_pressure_strong and not breakdown_entry and not retest_breakdown:
    score += 15
    set_signal("⚡ EARLY PUT (BREAKDOWN PRESSURE)", 70)

elif breakdown_pressure and not breakdown_entry and not retest_breakdown:
    set_signal("⚡ BREAKDOWN BUILDUP - WATCH PUT", 70)

elif breakdown_entry and not failed_breakdown:

    # Prevent repeated late entries
    if (
        st.session_state.last_signal !=
        "🚀 BUY PUT (BREAKDOWN ENTRY)"
    ):

        set_signal(
            "🚀 BUY PUT (BREAKDOWN ENTRY)",
            95
        )

        trade_signal = True

elif retest_breakdown:
    set_signal("🎯 BUY PUT (RETEST ENTRY)", 90)
    trade_signal = True

if bear_trap:
    if (
            price < vwap or
            price < ema or
            oi_bias != "BULLISH" or
            score < 60
    ):
        bear_trap = False

elif breakdown_setup and not breakdown_entry and not retest_breakdown:
    set_signal("⚡ BREAKDOWN BUILDUP - WATCH PUT", 55)

# 🚀 2. CONFIRMED MOVES
elif breakout_confirmed and not fake_breakout and price > vwap:
    set_signal("🚀 BUY CALL (CONFIRMED BREAKOUT)", 90)
    trade_signal = True

elif breakdown_confirmed and not fake_breakdown:
    set_signal("🚀 BUY PUT (CONFIRMED BREAKDOWN)", 90)
    trade_signal = True

elif rejection_confirmed:
    set_signal("🔥 SELL CALL / BUY PUT (REJECTION)", 90)
    trade_signal = True

elif breakout_retest:
    set_signal("🔥 BUY CALL (RETEST ENTRY)", 85)
    trade_signal = True

# ⚡ 3. EARLY INTELLIGENCE (UPGRADED)

elif breakout_anticipation and score > 55:
    set_signal("⚡ EARLY CALL (BREAKOUT BUILDUP)", 70)

elif breakdown_anticipation and score > 55:
    set_signal("⚡ EARLY PUT (BREAKDOWN BUILDUP)", 70)


# 🚨 TRAP ZONE FILTER (NEW - CRITICAL)
if (
    trap_score >= 70
    and abs(price - resistance) < 20
    and price < resistance
):
    set_signal("🚨 TRAP ZONE NEAR RESISTANCE - AVOID CALL", 95)

bull_trap_confirmed_entry = (
    bull_trap
    and trap_score >= 70
    and price < vwap
    and df5["close"].iloc[-1] < df5["close"].iloc[-2]  # follow-through
    and df5["fut_volume"].iloc[-1] > df5["vol_ma"].iloc[-1] * 0.8
)


if bull_trap_confirmed_entry:
    set_signal("🔥 BUY PUT (BULL TRAP CONFIRMATION)", 96)
    trade_signal = True


if "BEAR TRAP" in signal and "REVERSAL" not in signal:
    if not (price > vwap and price > ema and oi_bias == "BULLISH"):
        set_signal("NO TRADE", 10)

if "BULL TRAP" in signal and "REVERSAL" not in signal:
    if not (price < vwap and price < ema and oi_bias == "BEARISH"):
        set_signal("NO TRADE", 10)

# 🧠 NEW: Breakout pressure (early heads-up BEFORE signal)
elif (
    trend_continuation
    and breakout_pressure
    and score > 40
    and not bull_trap
    and trap_score < 70
    and abs(price - resistance) > 15
    and df5["fut_volume"].iloc[-1] > 0.7 * df5["vol_ma"].iloc[-1]
):
    set_signal("⚡ TREND CONTINUATION - EARLY CALL", 70)

elif (
    breakout_pressure
    and score > 40
    and trend15 == "BULLISH"
    and price > vwap
    and not bull_trap
    and trap_score < 70
    and breakout_confirmed
):
    set_signal("⚡ BREAKOUT BUILDUP - WATCH CALL", 65)

elif breakdown_pressure and not retest_breakdown and not breakdown_entry:
    set_signal("⚡ BREAKDOWN BUILDUP - WATCH PUT", 65)

# 📉 4. STRUCTURE FILTERS
elif (
        price < resistance  # ✅ FIX: ensure actually below resistance
        and abs(price - resistance) < resistance_buffer
        and df5["fut_volume"].iloc[-1] < df5["vol_ma"].iloc[-1]
        and breakout_strength < 50
):
    set_signal("⚠️ BELOW RESISTANCE - WAIT", 60)


# 🚨 CRITICAL FIX: BLOCK FAKE BUY NEAR RESISTANCE
if (
    price < resistance and
    (resistance - price) < 25 and
    not breakout_confirmed and
    breakout_strength < 65
):
    set_signal("⚠️ BREAKOUT BUILDUP - WAIT FOR CONFIRMATION", 85)
    score -= 10



if (
    price > vwap and price > ema and
    oi_bias == "BULLISH" and
    smart_money == "BULLISH BUILDUP" and
    30 <= breakout_strength < 60 and
    price < resistance
):
    set_signal("⚠️ WEAK BULLISH CONTINUATION - WAIT FOR BREAK", 60)


elif (
        abs(price - vwap) < 40
        and not breakout_pressure
        and score < 70
):
    set_signal("⚠️ RANGE - NO TRADE", 50)


# 🚀 5. MOMENTUM BASED
elif breakout_strength > 70 and score > 65:
    set_signal("BUY CALL" if trend15 == "BULLISH" else "BUY PUT", 65)
    trade_signal = True

elif breakout_strength > 50 and score > 55:
    set_signal("EARLY CALL" if trend15 == "BULLISH" else "EARLY PUT", 55)

if breakout_confirmed and price > resistance and score >= 70:
    set_signal("⚡ MOMENTUM BREAKOUT - LATE ENTRY / WAIT RETEST", 85)


if breakout_confirmed and (price - resistance) > 20:
    set_signal("⚠️ LATE BREAKOUT - WAIT FOR RETEST", 90)
    score -= 15


if breakout_confirmed:
    if price < vwap or smart_money == "BEARISH BUILDUP":
        set_signal("⚠️ INVALID BREAKOUT - WAIT", 85)
        score -= 20


if entry_quality < 40:
    set_signal("⚠️ MOVE DONE - WAIT", 85)

# 🚀 VWAP RECLAIM INTELLIGENCE (NEXT LEVEL)
vwap_reclaim = (
        price > vwap and
        df5["close"].iloc[-2] < vwap and
        df5["fut_volume"].iloc[-1] > df5["vol_ma"].iloc[-1]
)

# ================= WEAK PULLBACK LOGIC (NEW - CRITICAL) =================

weak_pullback_call = (
    price > vwap and
    price > ema and
    breakout_strength >= 50 and
    df5["fut_volume"].iloc[-1] < df5["vol_ma"].iloc[-1]  # ⚠️ low volume
    and oi_trend != "STRONG BEARISH"  # avoid strong bearish OI
    and trap_score < 70
    and price < resistance  # still below resistance (pullback, not breakout)
)

if weak_pullback_call:
    set_signal("⚠️ WEAK BULLISH PULLBACK - SCALP ONLY", 60)

if vwap_reclaim and breakout_strength >= 50:
    score += 10

if vwap_reclaim:

    # ✅ Only boost score if HTF supports
    if trend15 == "BULLISH":
        score += 10
        set_signal("🚀 VWAP RECLAIM - STRONG BUY", 90)

    # ⚠️ Bearish context → downgrade (CRITICAL FIX)
    else:
        score += 5
        set_signal("⚠️ VWAP RECLAIM IN BEAR TREND - WAIT", 70)

# 🚨 BLOCK FAKE MOMENTUM (SHORT COVERING / LOW VOLUME)

fake_momentum = (
    df5["fut_volume"].iloc[-1] < df5["vol_ma"].iloc[-1]  # low volume
    or oi_trend == "STRONG BEARISH"
    or oi_bias == "LONG UNWINDING"
    or breakout_strength < 50
)

# ================= MOMENTUM / CONSOLIDATION ENGINE =================

bullish_consolidation = (
    price > ema
    and price > (vwap - 20)
    and df5["close"].iloc[-1] >
        df5["close"].iloc[-5]
    and breakout_strength < 40
    and abs(price - resistance) > 40
)

real_fake_momentum = (
    fake_momentum
    and price > resistance
    and breakout_strength < 40
    and df5["close"].iloc[-1] <
        df5["close"].iloc[-2]
)

if (
    price > resistance
    and price > vwap
    and breakout_strength >= 50
    and df5["fut_volume"].iloc[-1] > df5["vol_ma"].iloc[-1]
    and score > 70
    and not real_fake_momentum
):
    set_signal("🚀 STRONG BUY CALL - MOMENTUM", 95)
    signal_strength = 95
    trade_signal = True

elif bullish_consolidation:

    # 🚀 continuation pause
    if trend15 == "BULLISH":
        set_signal(
            "🟡 BULLISH CONSOLIDATION - WATCH CALL",
            72
        )

    else:
        set_signal(
            "⚠️ SIDEWAYS CONSOLIDATION - WAIT",
            60
        )

elif real_fake_momentum:
    set_signal(
        "⚠️ SHORT COVERING BOUNCE - WAIT",
        90
    )
    score -= 10

# ================= LATE ENTRY FILTER =================

too_extended_up = (
    price > vwap
    and (price - vwap) > 60
    and breakout_strength < 70
)

if too_extended_up:
    set_signal("⚠️ TOO LATE TO BUY - WAIT PULLBACK", 92)
    trade_signal = False

# 🔥 Preserve strong signals (avoid override bug)
#if signal_strength >= 85:
#    pass
#elif "TRAP REVERSAL" not in signal:
#    if oi_trend == "WEAK" and score < 60:
#        set_signal("NO TRADE", 10)
#
#    if "CALL" in signal and oi_bias != "BULLISH":
#        set_signal("WAIT", 20)
#
#    if "PUT" in signal and oi_bias != "BEARISH":
#        set_signal("WAIT", 20)





# ---------------- SIGNAL FALLBACK ----------------

if not signal or signal.strip() == "":
    set_signal("⚠️ NO CLEAR SIGNAL", 20)

prev_signal = st.session_state.last_signal

# ---------------- SIGNAL STABILITY (FIXED) ----------------

if not st.session_state.last_signal:
    pass  # don't update yet

elif st.session_state.last_signal != signal:
    if signal_strength < 60:
        set_signal(st.session_state.last_signal, signal_strength)


# ================= CONTEXT-AWARE SIGNAL FIX =================

if breakout_confirmed and "HTF BEARISH" in signal:
    set_signal("⚠️ COUNTER-TREND BREAKOUT - WAIT", 70)

if breakout_confirmed and "HTF BULLISH" in signal:
    set_signal("⚠️ COUNTER-TREND BREAKDOWN - WAIT", 70)



# ---------------- MTF BLOCKER ----------------

# Block trades against higher timeframe
if trend1h == "BEARISH" and "CALL" in signal and "REVERSAL" not in signal:

    # 🚀 STRONG STRUCTURE OVERRIDE (NEW FIX)
    if (
        breakout_strength >= 70
        and price > vwap
        and price > ema
        and df5["fut_volume"].iloc[-1] > df5["vol_ma"].iloc[-1]
    ):
        set_signal("🚀 TREND REVERSAL CONFIRMED - BUY CALL", 95)
        trade_signal = True
        score += 10

    # ⚡ Weak counter trend
    elif breakout_strength >= 50 and price > vwap:
        set_signal("⚠️ COUNTER TREND CALL - QUICK TRADE", 70)
        score -= 5

    # ❌ Block bad trades
    else:
        set_signal("⚠️ HTF BEARISH - NO CALL", 85)
        score -= 15

if trend1h == "BULLISH" and "PUT" in signal and "REVERSAL" not in signal:



    # 🚨 STRONG BEARISH REVERSAL (mirror of CALL logic)
    if (
        breakout_strength >= 70
        and price < vwap
        and price < ema
        and df5["fut_volume"].iloc[-1] > df5["vol_ma"].iloc[-1]
    ):
        set_signal("🚀 TREND REVERSAL CONFIRMED - BUY PUT", 95)
        trade_signal = True
        score += 10

    # ⚡ Weak counter-trend
    elif breakout_strength >= 50 and price < vwap:
        set_signal("⚠️ COUNTER TREND PUT - QUICK TRADE", 70)
        score -= 5

    # ❌ Block bad trades
    else:
        set_signal("⚠️ HTF BULLISH - NO PUT", 85)
        score -= 15

if "HTF BEARISH" in signal:
    score = min(score, 55)

if "HTF BULLISH" in signal:
    score = min(score, 55)

# 🚨 FINAL SAFETY FILTER (MASTER RULE)
if "BUY CALL" in signal and (price < vwap or price < ema):
    set_signal("NO TRADE", 10)
    trade_signal = True

if "BUY PUT" in signal and (price > vwap and price > ema):
    set_signal("⚠️ FALSE BEARISH SIGNAL - TREND ABOVE VWAP", 90)
    score -= 15

# ---------------- DECISION ENGINE (MTF FILTER) ----------------

aligned_bull = trend1h == "BULLISH" and trend15 == "BULLISH"
aligned_bear = trend1h == "BEARISH" and trend15 == "BEARISH"

# Final direction sanity
if price > vwap and price > ema:
    if "PUT" in signal:
        set_signal("⚠️ WRONG SIDE - ABOVE VWAP", 95)
        score -= 15

if price < vwap and price < ema:
    if "CALL" in signal:
        set_signal("⚠️ WRONG SIDE - BELOW VWAP", 95)
        score -= 15

if "BUY PUT" in signal:
    if "BREAKDOWN ENTRY" in signal or "RETEST ENTRY" in signal:
        decision = "ENTER TRADE"
        trade_signal = True
    else:
        decision = "WAIT"

elif "BUY CALL" in signal and aligned_bull:
    decision = "ENTER TRADE"
    trade_signal = True

elif "BUY PUT" in signal and aligned_bear:
    decision = "ENTER TRADE"
    trade_signal = True

elif "REVERSAL" in signal:
    decision = "ENTER TRADE"
    trade_signal = True

elif "TRAP" in signal:
    decision = "AVOID TRADE"
    score = min(score, 40)

else:
    decision = "WAIT"

if "EARLY PUT" in signal:
    decision = "WATCH / EARLY ENTRY"

elif "BREAKDOWN BUILDUP" in signal:
    if near_support:
        decision = "WATCH"
    else:
        decision = "WAIT"

if "PRE-BREAKDOWN" in signal:
    decision = "WATCH"

elif "STRONG BREAKDOWN" in signal:
    decision = "ENTER TRADE"

lots = get_position_size(score, breakout_strength, volume_spike)

# 🚨 FORCE minimum lots for valid trades
if decision == "ENTER TRADE":
    lots = max(lots, 1)
else:
    lots = 0

# ---------------- TRADE CONTEXT AWARENESS ----------------

if st.session_state.trade:

    current_trade_type = st.session_state.trade["type"]

    # 🚨 EXIT LOGIC (NOT HOLD)
    if current_trade_type == "CE" and (
            price < vwap and price < ema
    ):
        send_telegram("⚠️ EXIT CALL - STRUCTURE BROKEN")
        st.session_state.trade = None

    elif current_trade_type == "PE" and (
            price > vwap and price > ema
    ):
        send_telegram("⚠️ EXIT PUT - STRUCTURE BROKEN")
        st.session_state.trade = None

# ---------------- TRADE COOLDOWN ----------------

cooldown_ok = True

if st.session_state.last_trade_time:
    last_time = pd.to_datetime(st.session_state.last_trade_time)
    current_time = df5["date"].iloc[-1]

    # 10 min cooldown (2 candles)
    if (current_time - last_time).seconds < 600:
        cooldown_ok = False

volume_ok = (
        df5["fut_volume"].iloc[-1] > 0.5 * df5["vol_ma"].iloc[-1]
)

# 🔥 SMART EARLY ENTRY (ONLY HIGH QUALITY)

strong_early_entry = (
        ("BREAKOUT BUILDUP" in signal or "TREND CONTINUATION" in signal)
        and score >= 75
        and breakout_strength >= 50
        and oi_bias == "BULLISH"
        and price > vwap
        and price > ema
        and trend15 == "BULLISH"
)

valid_trade_signal = (
    trade_signal
    and decision == "ENTER TRADE"
    and decision != "WAIT_FOR_BREAKDOWN"
    and (
            signal_strength >= 85  # stricter
            and (
                    "BUY CALL" in signal
                    or "BUY PUT" in signal
            )
    )
    and cooldown_ok
    and volume_ok
    and lots > 0
)

if (
        any(x in signal for x in ["EARLY", "WATCH", "BUILDUP", "RANGE"])
        and not strong_early_entry
):
    valid_trade_signal = False


def get_signal_stage(signal):
    if "EARLY" in signal or "BUILDUP" in signal or "WATCH" in signal:
        return "EARLY"
    elif "CONFIRMED" in signal or "RETEST" in signal:
        return "CONFIRMED"
    elif "STRONG" in signal or "MOMENTUM" in signal:
        return "MOMENTUM"
    else:
        return "NONE"


stage_rank = {
    "NONE": 0,
    "EARLY": 1,
    "CONFIRMED": 2,
    "MOMENTUM": 3
}


current_stage = get_signal_stage(signal)
prev_stage = st.session_state.last_stage

stage_changed = current_stage != prev_stage

NO_TRADE_CONTEXT = (
    (
        low_volume
        or post_move_pause
    )
    and not (
        breakdown_pressure_strong
        or breakdown_pressure
        or pre_breakdown_zone
        or trend_continuation_bear
        or continuation_active  # 🔥 ADD THIS
    )
)

if NO_TRADE_CONTEXT and not pre_breakdown_zone:
    set_signal("⚠️ NO TRADE ZONE - WAIT", 100)
    score = min(score, 50)

perfect_put_entry = (
    vwap_rejection_confirmed and
    df5["close"].iloc[-1] < df5["low"].iloc[-3] and
    df5["fut_volume"].iloc[-1] > df5["vol_ma"].iloc[-1]
)

if perfect_put_entry:
    set_signal("💎 PERFECT PUT ENTRY", 100)

chop_zone = (
    abs(price - vwap) < 80
    and df5["fut_volume"].iloc[-1] < df5["vol_ma"].iloc[-1]
    and breakout_strength < 40
    and abs(df5["close"].iloc[-1] - df5["close"].iloc[-5]) < 40
    and not (breakdown_pressure_strong or breakdown_pressure or pre_breakdown_zone)
)

chop_structure = (
    abs(price - vwap) < 35 and
    breakout_strength < 40 and
    abs(df5["close"].iloc[-1] - df5["close"].iloc[-5]) < 30
)

# Don't override active bearish pressure states
if (
    (chop_zone or chop_structure)
    and not (
        breakdown_pressure
        or breakdown_pressure_strong
        or pre_breakdown_zone
        or trend_continuation_bear
    )
):
    set_signal("⚠️ CHOP ZONE - AVOID TRADING", 100)

if breakdown_pressure_strong:
    score += 10

elif breakdown_pressure:
    score += 5

compression = (
    (df5["high"].tail(6).max() -
     df5["low"].tail(6).min()) < 45
)

if compression and df5["fut_volume"].iloc[-1] < df5["vol_ma"].iloc[-1] * 0.4:
    set_signal("⚠️ VOLATILITY COMPRESSION - WAIT", 100)

# ================= LATE MOVE FILTER =================

late_breakdown = (
    price < support
    and abs(price - support) > 40
)

if late_breakdown:
    set_signal("⚠️ LATE BREAKDOWN - WAIT PULLBACK", 90)
    score -= 15


# ================= LATE BREAKDOWN BLOCKER =================

already_extended_breakdown = (
    price < support
    and (
        support - price
    ) > 45
    and df5["fut_volume"].iloc[-1] <
        df5["vol_ma"].iloc[-1]
)

if already_extended_breakdown:

    set_signal(
        "⚠️ BREAKDOWN EXTENDED - WAIT RETEST",
        95
    )

    trade_signal = False
    score -= 20



if "PRE-BREAKDOWN" in signal:
    valid_trade_signal = False

if "BUILDUP" in signal:
    valid_trade_signal = False

# ---------------- ENTRY ----------------
stage_upgrade = (
    stage_changed and
    stage_rank.get(current_stage, 0) > stage_rank.get(prev_stage, 0)
)

signal_upgrade = (
        prev_signal != signal and
        signal_strength > 80
)

# 🚨 FINAL FILTER - NO FAKE SIGNALS
if any(x in signal for x in ["WAIT", "WATCH", "BUILDUP", "NO TRADE", "RANGE"]):
    valid_trade_signal = False

min_time_gap = 120  # seconds

now = datetime.datetime.now()

if st.session_state.last_alert_time:
    diff = (now - st.session_state.last_alert_time).seconds
else:
    diff = 999

can_send = diff > min_time_gap

valid_trade_signal = signal in EXECUTABLE_SIGNALS

if (
        st.session_state.trade is None
        and valid_trade_signal
        and (
            stage_upgrade
            or current_stage == "CONFIRMED"
            or "RETEST" in signal
            or "BREAKDOWN ENTRY" in signal
        )
        and can_send
):
    strike = select_strike(price, signal)
    opt_type = "CE" if "CALL" in signal else "PE"
    option_price = get_option_price(strike, opt_type)

    st.session_state.trade = {
        "type": opt_type,
        "strike": strike,
        "entry": option_price,
        "sl": option_price - 20,
        "target": option_price + 40,
        "lots": lots,
        "partial": False
    }

    msg = f"""
    🚀 TRADE ALERT

    {signal}

    ━━━━━━━━━━━━━━━
    🎯 {opt_type} {strike}
    💰 Entry: {round(option_price, 2)}

    📦 Lots: {lots}

    📊 Spot: {round(price, 2)}
    VWAP: {round(vwap, 2)} | EMA: {round(ema, 2)}

    📈 Trend: {trend15} / {trend1h}
    📊 OI: {oi_bias} ({oi_trend})

    🧠 Score: {score}
    ━━━━━━━━━━━━━━━
    """

    send_telegram(msg)
    st.session_state.last_stage = current_stage
    st.session_state.last_signal = signal
    st.session_state.last_alert_time = now
    log = {
        "time": str(datetime.datetime.now()),
        "signal": signal,
        "type": opt_type,
        "strike": strike,
        "entry": option_price,
        "exit": None,
        "result": "OPEN",
        "pnl": 0,
        "oi_ce": int(oi_ce),
        "oi_pe": int(oi_pe),
        "oi_ce_change": int(oi_ce_change),
        "oi_pe_change": int(oi_pe_change),
        "oi_ratio": round(oi_ratio, 2),
        "oi_trend": oi_trend,
        "smart_money": smart_money,
    }

    st.session_state.trade_logs.append(log)
    save_trade_logs(st.session_state.trade_logs)
    st.session_state.last_trade_time = df5["date"].iloc[-1]

# ---------------- MANAGEMENT (FIXED) ----------------
if st.session_state.trade:

    t = st.session_state.trade

    # Safety check
    if "strike" not in t:
        st.warning("Old trade removed")
        st.session_state.trade = None

    else:
        opt_price = get_option_price(t["strike"], t["type"])
        pnl = opt_price - t["entry"]

        # Partial
        if pnl > 15 and not t.get("partial"):
            t["partial"] = True
            send_telegram(f"💰 PARTIAL @ {opt_price}")

        # Trail SL
        if pnl > 25:
            t["sl"] = t["entry"]

        # Exit SL
        if opt_price <= t["sl"]:
            send_telegram(f"❌ SL HIT @ {opt_price}")
            st.session_state.trade = None

        # Exit Target
        elif pnl > 50:
            send_telegram(f"🎯 TARGET HIT @ {opt_price}")
            st.session_state.trade = None

        if opt_price <= t["sl"]:

            pnl = opt_price - t["entry"]

            for log in reversed(st.session_state.trade_logs):
                if log["result"] == "OPEN":
                    log["exit"] = opt_price
                    log["pnl"] = pnl
                    log["result"] = "LOSS" if pnl < 0 else "WIN"
                    break

            save_trade_logs(st.session_state.trade_logs)

            send_telegram(f"❌ SL HIT @ {opt_price}")
            st.session_state.trade = None
        elif pnl > 50:

            for log in reversed(st.session_state.trade_logs):
                if log["result"] == "OPEN":
                    log["exit"] = opt_price
                    log["pnl"] = pnl
                    log["result"] = "WIN"
                    break

            save_trade_logs(st.session_state.trade_logs)

            send_telegram(f"🎯 TARGET HIT @ {opt_price}")
            st.session_state.trade = None


# ---------------- UI (PRO DASHBOARD) ----------------
score = max(0, min(100, score))
st.title("📊 AI Trading System PRO MAX")

# ================= TOP METRICS (MOBILE FIRST) =================

st.markdown("### 📊 Market Snapshot")

st.markdown(f"""
<div class="metric">
📈 <b>Price:</b> {round(price, 2)} <br>
📊 <b>VWAP:</b> {round(vwap, 2)} <br>
📉 <b>EMA:</b> {round(ema, 2)} <br><br>

🧭 <b>15m Trend:</b> {trend15} <br>
🧭 <b>1H Trend:</b> {trend1h} <br>
🎯 <b>Score:</b> {score}
</div>
""", unsafe_allow_html=True)

def get_progress(score):
    return max(0.0, min(1.0, (score + 100) / 200))

st.progress(get_progress(score))


#==========Signals UI=================

st.markdown("### 🚀 Signal")

show_signal(signal)

st.markdown(f"**Decision:** {decision}")

# ================= MARKET STRUCTURE =================

st.markdown("### 📊 Market Structure")

st.dataframe(pd.DataFrame({
    "Metric": ["Resistance", "Support", "Breakout Strength", "Volume Spike"],
    "Value": [
        round(resistance, 2),
        round(support, 2),
        breakout_strength,
        volume_spike
    ]
}), use_container_width=True)

# ================= PRICE ACTION =================

st.markdown("### 🧠 Price Action")

st.dataframe(pd.DataFrame({
    "Signal": ["Bull Trap", "Bear Trap", "Rejection", "Breakout Confirmed"],
    "Status": [
        bull_trap,
        bear_trap,
        rejection,
        breakout_confirmed
    ]
}), use_container_width=True)

# ================= OI =================

st.markdown("### 📊 OI Intelligence")

st.dataframe(pd.DataFrame({
    "Metric": ["CE", "PE", "CE Δ", "PE Δ", "Ratio", "Trend", "Bias"],
    "Value": [
        int(oi_ce),
        int(oi_pe),
        int(oi_ce_change),
        int(oi_pe_change),
        round(oi_ratio, 2),
        oi_trend,
        oi_bias
    ]
}), use_container_width=True)

# ================= DECISION =================

st.markdown("### 🧠 Decision Engine")

st.dataframe(pd.DataFrame({
    "Factor": ["Decision", "Lots", "Smart Money"],
    "Value": [decision, lots, smart_money]
}), use_container_width=True)

# ================= TRADE =================
if st.session_state.trade:
    st.subheader("💼 Active Trade")

    t = st.session_state.trade

    st.markdown(f"""
    <div class="metric">
    <b>{t['type']} {t['strike']}</b><br>
    Entry: {t['entry']}<br>
    SL: {t['sl']} | Target: {t['target']}<br>
    Lots: {t.get('lots', 1)}
    </div>
    """, unsafe_allow_html=True)

# ================= PERFORMANCE =================
st.subheader("📊 Performance")

logs = pd.DataFrame(st.session_state.trade_logs)

if not logs.empty:
    total = len(logs)
    wins = len(logs[logs["result"] == "WIN"])
    losses = len(logs[logs["result"] == "LOSS"])
    win_rate = (wins / total) * 100 if total else 0
    pnl = logs["pnl"].sum()

    st.dataframe(pd.DataFrame({
        "Metric": ["Trades", "Wins", "Losses", "Win Rate", "PnL"],
        "Value": [total, wins, losses, f"{round(win_rate, 2)}%", round(pnl, 2)]
    }), use_container_width=True)

# ================= LOGS =================
with st.expander("📜 Trade Logs"):
    if st.session_state.trade_logs:
        st.dataframe(pd.DataFrame(st.session_state.trade_logs), use_container_width=True)

# ================= DEBUG =================
with st.expander("🔍 Debug Panel"):
    st.json({
        "price": float(price),
        "vwap": float(vwap),
        "ema": float(ema),
        "resistance": float(resistance),
        "support": float(support),
        "bull_trap": bool(bull_trap),
        "bear_trap": bool(bear_trap),
        "rejection": bool(rejection),
        "rejection_confirmed": bool(rejection_confirmed),
        "breakout_confirmed": bool(breakout_confirmed),
        "breakout_strength": int(breakout_strength),
        "score": int(score),
        "futures_volume": int(df5["fut_volume"].iloc[-1]),
        "volume_ma": float(df5["vol_ma"].iloc[-1]),
        "signal": signal,
        "oi_ce": int(oi_ce),
        "oi_pe": int(oi_pe),
        "oi_ratio": round(oi_ratio, 2),
        "oi_trend": oi_trend,
        "smart_money": smart_money,
        "oi_bias": oi_bias,
        "trap_score": int(trap_score)
    })
