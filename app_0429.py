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
.big-font { font-size:18px !important; font-weight:600; }
.card {
    padding:15px;
    border-radius:12px;
    background-color:#111;
    color:white;
    box-shadow:0 0 10px rgba(0,0,0,0.4);
}
.green { color:#00ff9f; font-weight:bold; }
.red { color:#ff4d4d; font-weight:bold; }
.yellow { color:#ffc107; font-weight:bold; }
.center { text-align:center; }
</style>
""", unsafe_allow_html=True)

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

# ---------------- VWAP ----------------
inst = pd.DataFrame(kite.instruments("NFO"))
fut = inst[(inst["name"] == "NIFTY") & (inst["instrument_type"] == "FUT")]
expiry = fut["expiry"].min()
token = int(fut[fut["expiry"] == expiry].iloc[0]["instrument_token"])

df_fut = pd.DataFrame(kite.historical_data(
    token,
    datetime.datetime.now() - datetime.timedelta(days=2),
    datetime.datetime.now(),
    "5minute"
))

df_fut["date"] = pd.to_datetime(df_fut["date"])
today = df_fut["date"].dt.date.iloc[-1]
df_today = df_fut[df_fut["date"].dt.date == today]

df_today["cum_vol"] = df_today["volume"].cumsum()
df_today["cum_val"] = (df_today["close"] * df_today["volume"]).cumsum()
df_today["VWAP"] = df_today["cum_val"] / df_today["cum_vol"]

vwap = df_today["VWAP"].iloc[-1]

# ================= FUTURES VOLUME MAPPING =================

# Align futures volume with df5 timestamps
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
def set_signal(new_signal, strength):
    global signal, signal_strength
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

    return resistance, support


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

    return breakout and weak_breakout and no_follow


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
    if last["close"] > prev["close"]:
        strength += 20

    # VWAP shift (VERY IMPORTANT)
    if last["close"] < vwap:
        strength += 20
    if last["close"] > vwap:
        strength += 20

    # Volume expansion
    vol = df["fut_volume"].iloc[-1]
    vol_ma = df["vol_ma"].iloc[-1]

    if vol > 1.5 * vol_ma:
        strength += 20
    elif vol > vol_ma:
        strength += 10

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

smart_money = "BEARISH BUILDUP" if oi_ce > oi_pe else "BULLISH BUILDUP"

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

if trend15 == "BULLISH" and price > ema: score += 15
if trend15 == "BEARISH" and price < ema: score += 15

if price > vwap and trend15 == "BULLISH": score += 15
if price < vwap and trend15 == "BEARISH": score += 15

if strong: score += 10
if volume_spike: score += 10

if smart_money == "BULLISH BUILDUP" and trend15 == "BULLISH": score += 15
if smart_money == "BEARISH BUILDUP" and trend15 == "BEARISH": score += 15

# OI Trend (NEW - powerful)
if oi_trend == "STRONG BULLISH" and trend15 == "BULLISH":
    score += 20

elif oi_trend == "STRONG BEARISH" and trend15 == "BEARISH":
    score += 20

elif oi_trend == "WEAK":
    score -= 10

if trend1h == trend15:
    score += 10

if trend1h == trend15 == ("BULLISH" if price > ema else "BEARISH"):
    score += 10

# filters
ema_slope = df5["EMA"].iloc[-1] - df5["EMA"].iloc[-5]
if abs(ema_slope) < 5: score -= 20

price_move = abs(price - df5["close"].iloc[-10])
if price_move > 80: score -= 15

score = max(0, min(100, score))

# ================= NEW INTELLIGENCE LAYER =================
signal = "NO TRADE"
signal_strength = 0
resistance, support = detect_levels(df5)

bull_trap = is_bull_trap(df5, resistance)
bear_trap = is_bear_trap(df5, support)

trap_score = trap_strength(df5, vwap)

rejection = is_resistance_rejection(df5, resistance)

if rejection and not volume_spike:
    rejection = False

rejection_confirmed = rejection and df5.iloc[-1]["close"] < df5.iloc[-2]["low"]
breakout_confirmed = is_breakout_confirmed(df5, resistance)
if breakout_confirmed:
    resistance = resistance  # keep old resistance for few candles

breakout_strength = breakout_score(df5, vwap, ema)
breakdown_setup = is_breakdown_setup(df5, support, vwap)
breakdown_confirmed = (
        price < support
        and df5["close"].iloc[-1] < df5["close"].iloc[-2]
        and df5["fut_volume"].iloc[-1] > df5["vol_ma"].iloc[-1]
        and price < vwap
        and price < ema
)

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
if (
        oi_trend in ["STRONG BULLISH", "STRONG BEARISH"] and
        smart_money == "BEARISH BUILDUP" and
        abs(price - resistance) < 25
):
    market_state = "TRAP_ZONE"
    score -= 20
    trap_score += 15
    set_signal("🚨 LIKELY BULL TRAP ZONE", 80)


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
    score -= 15


# =========================
# AUTO BREAKDOWN ENTRY
# =========================
breakdown_entry = (
        price < support <= df5["close"].iloc[-2]
        and df5["close"].iloc[-1] < support
        and df5["fut_volume"].iloc[-1] > df5["vol_ma"].iloc[-1] * 1.2
        and price < vwap
        and price < ema
        and trap_score < 70
)


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
    signal = "⚠️ WEAK BREAKOUT ZONE - AVOID"

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

trend_continuation = (
        price > ema and
        price > vwap and
        trend15 == "BULLISH" and
        df5["close"].iloc[-1] > df5["close"].iloc[-3]
)

# Detect compression near support
breakdown_pressure = (
        price < vwap and
        price < ema and
        (price - support) < 30 and
        df5["fut_volume"].iloc[-1] > 0.3 * df5["vol_ma"].iloc[-1]
)

# Bull trap → go PUT
bull_trap_reversal = (
    bull_trap and
    trap_score >= 70 and
    price < vwap and
    df5["close"].iloc[-1] < df5["close"].iloc[-2] and
    df5["fut_volume"].iloc[-1] >= df5["vol_ma"].iloc[-1] * 0.8
)

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

# ---------------- SIGNAL (PRIORITY ENGINE) ----------------
# 🚨 FAKE STRENGTH FILTER (CRITICAL)
if (
    score >= 70 and
    price < vwap and
    df5["fut_volume"].iloc[-1] < df5["vol_ma"].iloc[-1] * 0.5
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

# 🚫 1. TRAPS (HIGHEST PRIORITY)
if bull_trap_reversal:
    set_signal("🔥 BUY PUT (BULL TRAP REVERSAL)", 95)

# 🔥 BEAR TRAP REVERSAL
elif bear_trap_reversal:
    set_signal("🔥 BUY CALL (BEAR TRAP REVERSAL)", 95)

elif bull_trap and trap_score >= 60 and price < vwap:
    set_signal("❌ BULL TRAP - AVOID CALL", 95)

elif bear_trap and trap_score >= 60 and price > vwap:
    set_signal("❌ BEAR TRAP - AVOID PUT", 95)

# 🚀 2. DIRECT ENTRIES
elif vwap_bounce and score >= 60:
    set_signal("🎯 BUY CALL (VWAP BOUNCE)", 85)

elif ema_bounce and score >= 55:
    set_signal("⚡ BUY CALL (EMA BOUNCE)", 75)

elif breakdown_entry:
    set_signal("🚀 BUY PUT (BREAKDOWN ENTRY)", 95)

elif retest_breakdown:
    set_signal("🎯 BUY PUT (RETEST ENTRY)", 90)

if bear_trap:
    if (
            price < vwap or
            price < ema or
            oi_bias != "BULLISH" or
            score < 60
    ):
        bear_trap = False


elif breakdown_entry:
    set_signal("🚀 BUY PUT (BREAKDOWN ENTRY)", 95)

elif retest_breakdown:
    set_signal("🎯 BUY PUT (RETEST ENTRY)", 90)

elif breakdown_setup and not breakdown_entry and not retest_breakdown:
    set_signal("⚡ BREAKDOWN BUILDUP - WATCH PUT", 55)

# 🚀 2. CONFIRMED MOVES
elif breakout_confirmed and price > vwap:
    set_signal("🚀 BUY CALL (CONFIRMED BREAKOUT)", 90)

elif breakdown_confirmed:
    set_signal("🚀 BUY PUT (CONFIRMED BREAKDOWN)", 90)

elif rejection_confirmed:
    set_signal("🔥 SELL CALL / BUY PUT (REJECTION)", 90)

elif breakout_retest:
    set_signal("🔥 BUY CALL (RETEST ENTRY)", 85)

# ⚡ 3. EARLY INTELLIGENCE (UPGRADED)

elif breakout_anticipation and score > 55:
    set_signal("⚡ EARLY CALL (BREAKOUT BUILDUP)", 75)

elif breakdown_anticipation and score > 55:
    set_signal("⚡ EARLY PUT (BREAKDOWN BUILDUP)", 75)

if "BEAR TRAP" in signal and "REVERSAL" not in signal:
    if not (price > vwap and price > ema and oi_bias == "BULLISH"):
        signal = "NO TRADE"

if "BULL TRAP" in signal and "REVERSAL" not in signal:
    if not (price < vwap and price < ema and oi_bias == "BEARISH"):
        signal = "NO TRADE"

# 🧠 NEW: Breakout pressure (early heads-up BEFORE signal)
elif trend_continuation and breakout_pressure and score > 40:
    set_signal("⚡ TREND CONTINUATION - EARLY CALL", 70)

elif (
        breakout_pressure
        and score > 40
        and trend15 == "BULLISH"
        and price > vwap
):
    set_signal("⚡ BREAKOUT BUILDUP - WATCH CALL", 65)

elif (
        breakdown_pressure
        and score > 40
        and trend15 == "BEARISH"
        and price < vwap
):
    set_signal("⚡ BREAKDOWN BUILDUP - WATCH PUT", 65)

# 📉 4. STRUCTURE FILTERS
elif (
        price < resistance  # ✅ FIX: ensure actually below resistance
        and abs(price - resistance) < resistance_buffer
        and df5["fut_volume"].iloc[-1] < df5["vol_ma"].iloc[-1]
        and breakout_strength < 50
):
    set_signal("⚠️ BELOW RESISTANCE - WAIT", 60)

elif (
        abs(price - vwap) < 40
        and not breakout_pressure
        and score < 70
):
    set_signal("⚠️ RANGE - NO TRADE", 50)


# 🚀 5. MOMENTUM BASED
elif breakout_strength > 70 and score > 65:
    set_signal("BUY CALL" if trend15 == "BULLISH" else "BUY PUT", 65)

elif breakout_strength > 50 and score > 55:
    set_signal("EARLY CALL" if trend15 == "BULLISH" else "EARLY PUT", 55)

if breakout_confirmed and price > resistance and score >= 70:
    set_signal("🚀 STRONG BUY CALL - MOMENTUM", 95)

if breakout_confirmed:
    if price < vwap or smart_money == "BEARISH BUILDUP":
        set_signal("⚠️ INVALID BREAKOUT - WAIT", 85)
        score -= 20

# 🚀 VWAP RECLAIM INTELLIGENCE (NEXT LEVEL)
vwap_reclaim = (
        price > vwap and
        df5["close"].iloc[-2] < vwap and
        df5["fut_volume"].iloc[-1] > df5["vol_ma"].iloc[-1]
)

if vwap_reclaim:
    score += 25
    set_signal("🚀 VWAP RECLAIM - STRONG BUY", 90)

if price > resistance and not breakout_confirmed:
    set_signal("⚡ ABOVE RESISTANCE - WATCH BREAKOUT", 70)

# 🚀 MOMENTUM OVERRIDE (VERY IMPORTANT)
if (
        price > resistance
        and price > vwap
        and breakout_strength > 60
        and df5["fut_volume"].iloc[-1] > df5["vol_ma"].iloc[-1]
        and score > 70
):
    set_signal("🚀 STRONG BUY CALL - MOMENTUM", 95)
    signal_strength = 95

# 🔥 Preserve strong signals (avoid override bug)
if signal_strength >= 85:
    pass
elif "TRAP REVERSAL" not in signal:
    if oi_trend == "WEAK" and score < 60:
        signal = "NO TRADE"

    if "CALL" in signal and oi_bias != "BULLISH":
        signal = "WAIT"

    if "PUT" in signal and oi_bias != "BEARISH":
        signal = "WAIT"

# ---------------- SIGNAL FALLBACK ----------------

if not signal or signal.strip() == "":
    signal = "⚠️ NO CLEAR SIGNAL"

prev_signal = st.session_state.last_signal

# ---------------- SIGNAL STABILITY (FIXED) ----------------

if not st.session_state.last_signal:
    pass  # don't update yet

elif st.session_state.last_signal != signal:
    if signal_strength < 60:
        signal = st.session_state.last_signal

# ---------------- MTF BLOCKER ----------------

# Block trades against higher timeframe
if trend1h == "BEARISH" and "CALL" in signal:
    signal = "⚠️ HTF BEARISH - NO CALL"

if trend1h == "BULLISH" and "PUT" in signal:
    signal = "⚠️ HTF BULLISH - NO PUT"

# 🚨 FINAL SAFETY FILTER (MASTER RULE)
if "BUY CALL" in signal and (price < vwap or price < ema):
    signal = "NO TRADE"

if "BUY PUT" in signal and (price > vwap or price > ema):
    signal = "NO TRADE"

# ---------------- DECISION ENGINE (MTF FILTER) ----------------

aligned_bull = trend1h == "BULLISH" and trend15 == "BULLISH"
aligned_bear = trend1h == "BEARISH" and trend15 == "BEARISH"

if "BUY PUT" in signal:
    if "BREAKDOWN ENTRY" in signal or "RETEST ENTRY" in signal:
        decision = "ENTER TRADE"
    else:
        decision = "WAIT"

elif "BUY CALL" in signal and aligned_bull:
    decision = "ENTER TRADE"

elif "BUY PUT" in signal and aligned_bear:
    decision = "ENTER TRADE"

elif "REVERSAL" in signal:
    decision = "ENTER TRADE"

elif "TRAP" in signal:
    decision = "AVOID TRADE"

else:
    decision = "WAIT"

if "BREAKDOWN BUILDUP" in signal:

    if near_support:
        decision = "WAIT_FOR_BREAKDOWN"
    else:
        decision = "WAIT"

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
        (
                "🚀 BUY CALL (CONFIRMED BREAKOUT)" in signal or
                "🔥 BUY CALL (BEAR TRAP REVERSAL)" in signal or
                "🔥 BUY PUT (BULL TRAP REVERSAL)" in signal or
                "🚀 BUY PUT (BREAKDOWN ENTRY)" in signal or
                "🎯 BUY PUT (RETEST ENTRY)" in signal or
                "🎯 BUY CALL (VWAP BOUNCE)" in signal or
                "⚡ BUY CALL (EMA BOUNCE)" in signal
        )
        and decision == "ENTER TRADE"
        and decision != "WAIT_FOR_BREAKDOWN"  # ✅ NEW FIX
        and signal_strength >= 80
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



# ---------------- ENTRY ----------------
stage_upgrade = (
    stage_changed and
    stage_rank.get(current_stage, 0) > stage_rank.get(prev_stage, 0)
)

signal_upgrade = (
        prev_signal != signal and
        signal_strength > 80
)

min_time_gap = 120  # seconds

now = datetime.datetime.now()

if st.session_state.last_alert_time:
    diff = (now - st.session_state.last_alert_time).seconds
else:
    diff = 999

can_send = diff > min_time_gap

if (
        st.session_state.trade is None
        and valid_trade_signal
        and (stage_upgrade or current_stage == "CONFIRMED")
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
        "type": opt_type,
        "strike": strike,
        "entry": option_price,
        "exit": None,
        "result": "OPEN",
        "pnl": 0
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

st.title("📊 AI Trading System PRO MAX")

# ================= TOP METRICS =================
col1, col2, col3, col4, col5, col6 = st.columns(6)

col1.metric("📈 Price", round(price, 2))
col2.metric("📊 VWAP", round(vwap, 2))
col3.metric("📉 EMA", round(ema, 2))
col4.metric("🧭 15m Trend", trend15)
col5.metric("🧭 1H Trend", trend1h)
col6.metric("🎯 Score", score)

st.progress(score / 100)

# ================= SIGNAL =================
st.subheader("🚀 Signal")

if decision == "ENTER TRADE":
    st.markdown(f"<h2 class='green center'>✅ {signal}</h2>", unsafe_allow_html=True)

elif decision == "WAIT":
    if not signal:
        signal = "⚠️ NO SIGNAL"
    color = "green" if "BUY" in signal else "red" if "TRAP" in signal else "yellow"
    st.markdown(f"<h2 class='{color} center'>{signal}</h2>", unsafe_allow_html=True)

else:
    st.markdown(f"<h2 class='red center'>❌ {signal}</h2>", unsafe_allow_html=True)

# ================= GRID =================
col1, col2 = st.columns(2)

# ---------- LEFT ----------
with col1:
    st.subheader("📊 Market Structure")

    st.dataframe(pd.DataFrame({
        "Metric": ["Resistance", "Support", "Breakout Strength", "Volume Spike"],
        "Value": [
            round(resistance, 2),
            round(support, 2),
            breakout_strength,
            volume_spike
        ]
    }), use_container_width=True)

    st.subheader("🧠 Price Action")

    st.dataframe(pd.DataFrame({
        "Signal": ["Bull Trap", "Bear Trap", "Rejection", "Rejection Confirmed", "Breakout Confirmed"],
        "Status": [
            bull_trap,
            bear_trap,
            rejection,
            rejection_confirmed,
            breakout_confirmed
        ]
    }), use_container_width=True)

# ---------- RIGHT ----------
with col2:
    st.subheader("📊 OI Intelligence")

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

    st.subheader("🧠 Decision Engine")

    st.dataframe(pd.DataFrame({
        "Factor": ["Decision", "Lots", "Smart Money"],
        "Value": [decision, lots, smart_money]
    }), use_container_width=True)

# ================= TRADE =================
if st.session_state.trade:
    st.subheader("💼 Active Trade")

    t = st.session_state.trade

    st.markdown(f"""
    <div class="card center">
        <h3>{t['type']} {t['strike']}</h3>
        <p>Entry: {t['entry']}</p>
        <p>SL: {t['sl']} | Target: {t['target']}</p>
        <p>Lots: {t.get('lots', 1)}</p>
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
st.subheader("📜 Trade Logs")

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
