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


#----------------------Trade Log File---------------------------------
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



#----------OI Trend-------------------------
if "oi_history" not in st.session_state:
    st.session_state.oi_history = load_oi_file()


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

trend15 = "BULLISH" if price15 > ema15 else "BEARISH"

# ---------------- VWAP ----------------
inst = pd.DataFrame(kite.instruments("NFO"))
fut = inst[(inst["name"]=="NIFTY") & (inst["instrument_type"]=="FUT")]
expiry = fut["expiry"].min()
token = int(fut[fut["expiry"]==expiry].iloc[0]["instrument_token"])

df_fut = pd.DataFrame(kite.historical_data(
    token,
    datetime.datetime.now()-datetime.timedelta(days=2),
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


# ================= TRAP + BREAKOUT INTELLIGENCE =================
def is_breakdown_setup(df, support, vwap):
    last = df.iloc[-1]

    near_support = last["close"] <= support * 1.002
    below_vwap = last["close"] < vwap

    return near_support and below_vwap

def detect_levels(df):
    recent = df.tail(20)
    resistance = recent["high"].max()
    support = recent["low"].min()
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
    df = inst[(inst["name"]=="NIFTY") & (inst["instrument_type"].isin(["CE","PE"]))]
    expiry = df["expiry"].min()
    df = df[df["expiry"]==expiry]

    base = round(price/50)*50
    strikes = [base-200, base-100, base, base+100, base+200]
    df = df[df["strike"].isin(strikes)]

    tokens = df["instrument_token"].tolist()
    quotes = kite.quote(tokens)

    df["oi"] = df["instrument_token"].apply(lambda x: quotes[str(x)]["oi"])
    return df

chain = get_option_chain(price)

oi_ce = chain[chain.instrument_type=="CE"]["oi"].sum()
oi_pe = chain[chain.instrument_type=="PE"]["oi"].sum()

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
if abs(oi_ce) < 1000: oi_ce = st.session_state.last_oi_ce
else: st.session_state.last_oi_ce = oi_ce

if abs(oi_pe) < 1000: oi_pe = st.session_state.last_oi_pe
else: st.session_state.last_oi_pe = oi_pe


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
    if score < 50:
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
    base = round(price/50)*50
    if "CALL" in signal:
        return base if "EARLY" in signal else base - 50
    if "PUT" in signal:
        return base if "EARLY" in signal else base + 50
    return base

def get_option_price(strike, opt_type):
    df = inst[(inst["name"]=="NIFTY") &
              (inst["strike"]==strike) &
              (inst["instrument_type"]==opt_type)]
    expiry = df["expiry"].min()
    token = int(df[df["expiry"]==expiry].iloc[0]["instrument_token"])
    return kite.quote([token])[str(token)]["last_price"]

# ---------------- CONFIDENCE ----------------
df5["vol_ma"] = df5["fut_volume"].rolling(20).mean()
volume_spike = df5["fut_volume"].iloc[-1] > 1.3 * df5["vol_ma"].iloc[-1]

last = df5.iloc[-1]
body = abs(last.close-last.open)
rng = last.high-last.low
strong = (body/rng)>0.5 if rng else False

score = 0

if trend15=="BULLISH" and price>ema: score+=15
if trend15=="BEARISH" and price<ema: score+=15

if price>vwap and trend15=="BULLISH": score+=15
if price<vwap and trend15=="BEARISH": score+=15

if strong: score+=10
if volume_spike: score+=10

if smart_money=="BULLISH BUILDUP" and trend15=="BULLISH": score+=15
if smart_money=="BEARISH BUILDUP" and trend15=="BEARISH": score+=15

# OI Trend (NEW - powerful)
if oi_trend == "STRONG BULLISH" and trend15 == "BULLISH":
    score += 20

elif oi_trend == "STRONG BEARISH" and trend15 == "BEARISH":
    score += 20

elif oi_trend == "WEAK":
    score -= 10

# filters
ema_slope = df5["EMA"].iloc[-1] - df5["EMA"].iloc[-5]
if abs(ema_slope) < 5: score -= 20

price_move = abs(price - df5["close"].iloc[-10])
if price_move > 80: score -= 15

score = max(0,min(100,score))

# ================= NEW INTELLIGENCE LAYER =================

resistance, support = detect_levels(df5)

bull_trap = is_bull_trap(df5, resistance)
bear_trap = is_bear_trap(df5, support)

rejection = is_resistance_rejection(df5, resistance)

if rejection and not volume_spike:
    rejection = False

rejection_confirmed = rejection and df5.iloc[-1]["close"] < df5.iloc[-2]["low"]
breakout_confirmed = is_breakout_confirmed(df5, resistance)
if breakout_confirmed and not volume_spike:
    breakout_confirmed = False

breakout_strength = breakout_score(df5, vwap, ema)

breakdown_setup = is_breakdown_setup(df5, support, vwap)

# ---------------- SIGNAL ----------------
signal = "NO TRADE"

if rejection and price > vwap:
    signal = "⚠️ WAIT - ABOVE VWAP"

# 🚫 TRAP FILTER (highest priority)
if bull_trap:
    signal = "❌ BULL TRAP - AVOID CALL"

elif bear_trap:
    signal = "❌ BEAR TRAP - AVOID PUT"

elif rejection_confirmed and trend15 != "STRONG BULLISH":
    signal = "🔥 SELL CALL / BUY PUT (REJECTION)"

elif breakout_confirmed and price > vwap:
    signal = "🚀 BUY CALL (CONFIRMED BREAKOUT)"

elif breakdown_setup:
    signal = "⚠️ BREAKDOWN SETUP - WATCH FOR PE"

# 📉 RANGE FILTER (avoid chop)
elif abs(price - vwap) < 40:
    signal = "⚠️ RANGE - NO TRADE"

# 🚀 STRONG BREAKOUT
elif breakout_strength > 70 and score > 65:
    signal = "BUY CALL" if trend15=="BULLISH" else "BUY PUT"

# ⚠️ EARLY SETUP
elif breakout_strength > 50 and score > 55:
    signal = "EARLY CALL" if trend15=="BULLISH" else "EARLY PUT"

if oi_trend == "WEAK":
    signal = "NO TRADE"

# Context-based filtering (NEW)
if "CALL" in signal and oi_bias != "BULLISH":
    signal = "WAIT"

if "PUT" in signal and oi_bias != "BEARISH":
    signal = "WAIT"


decision = "WAIT"

# 🚫 TRAP = highest priority
if bull_trap or bear_trap:
    decision = "AVOID TRADE"

# ✅ confirmed setups only
elif rejection_confirmed:
    decision = "ENTER TRADE"

elif breakout_confirmed:
    decision = "ENTER TRADE"

# ⚡ strong confidence
elif score > 60:
    decision = "ENTER TRADE"

else:
    decision = "WAIT"


lots = get_position_size(score, breakout_strength, volume_spike)

# Safety override (VERY IMPORTANT)
if decision != "ENTER TRADE":
    lots = 0


# ---------------- ENTRY ----------------
if st.session_state.trade is None and decision == "ENTER TRADE" and lots > 0:

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

    send_telegram(f"ENTRY {opt_type} {strike} @ {option_price}")
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

# ---------------- UI ----------------

st.title("📊 AI Trading System PRO MAX")

st.metric("Price", round(price,2))
st.metric("EMA", round(ema,2))
st.metric("VWAP", round(vwap,2))

st.write(f"Trend: {trend15}")
st.write(f"Smart Money: {smart_money}")

st.subheader(f"📊 Confidence ({score})")
st.progress(score/100)

st.subheader(f"🚀 Signal: {signal}")

st.subheader("📊 OI Trend Intelligence")
st.write(f"OI Trend: {oi_trend}")

if bull_trap:
    st.error("⚠️ Bull Trap Detected")
elif bear_trap:
    st.error("⚠️ Bear Trap Detected")


# AI Decision
st.subheader("🧠 AI Decision")

if decision == "ENTER TRADE":
    st.success("ENTER TRADE")

elif decision == "WAIT":
    st.warning("WAIT")

else:
    st.error("AVOID TRADE")

st.write(f"Position Size (Lots): {lots}")

# Commentary
def commentary():
    if signal=="NO TRADE":
        return "Market is choppy. Avoid trading."
    if "EARLY" in signal:
        return "Early entry. Manage risk."
    if score>70:
        return "Strong setup."
    return "Moderate setup."

st.info(commentary())

st.write(f"OI Bias: {oi_bias}")

st.write(f"Rejection Detected: {rejection}")
st.write(f"Rejection Confirmed: {rejection_confirmed}")

if rejection_confirmed:
    st.error("🚨 Confirmed Resistance Rejection - Strong Sell Signal")

if rejection:
    st.error("🚨 Resistance Rejection - Sellers Active")

st.write(f"Breakout Confirmed: {breakout_confirmed}")

if breakout_confirmed:
    st.success("🚀 Strong Breakout - Momentum Trade")


st.subheader("🧠 Smart Price Action ")
st.write(f"Resistance: {round(resistance,2)}")
st.write(f"Support: {round(support,2)}")
st.write(f"Breakout Strength: {breakout_strength}")

if st.session_state.trade:
    st.subheader("💼 Active Trade")
    st.write(st.session_state.trade)

st.subheader("📜 Trade Logs")

if st.session_state.trade_logs:
    df_logs = pd.DataFrame(st.session_state.trade_logs)
    st.dataframe(df_logs, use_container_width=True)

st.subheader("📊 Performance")

logs = pd.DataFrame(st.session_state.trade_logs)

if not logs.empty:
    total = len(logs)
    wins = len(logs[logs["result"] == "WIN"])
    losses = len(logs[logs["result"] == "LOSS"])

    win_rate = (wins / total) * 100 if total else 0
    total_pnl = logs["pnl"].sum()

    st.write(f"Total Trades: {total}")
    st.write(f"Wins: {wins}")
    st.write(f"Losses: {losses}")
    st.write(f"Win Rate: {round(win_rate,2)}%")
    st.write(f"Total PnL (pts): {round(total_pnl,2)}")

st.write(df5.tail(5))
st.subheader("🔍 Debug Panel")

st.write({
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
    "oi_ce_change": int(oi_ce_change),
    "oi_pe_change": int(oi_pe_change),
    "oi_ratio": round(oi_ratio, 2),
    "oi_trend": oi_trend,
    "smart_money": smart_money,
    "oi_bias": oi_bias
})