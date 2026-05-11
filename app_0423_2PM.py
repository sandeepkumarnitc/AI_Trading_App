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

smart_money = "BULLISH BUILDUP" if oi_ce > oi_pe else "BEARISH BUILDUP"

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
df5["vol_ma"] = df5["volume"].rolling(20).mean()
volume_spike = df5["volume"].iloc[-1] > 1.3 * df5["vol_ma"].iloc[-1]

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



# ---------------- SIGNAL ----------------
signal = "NO TRADE"

if score >= 70:
    signal = "BUY CALL" if trend15=="BULLISH" else "BUY PUT"
elif score >= 60:
    signal = "EARLY CALL" if trend15=="BULLISH" else "EARLY PUT"

if oi_trend == "WEAK":
    signal = "NO TRADE"

if "CALL" in signal and oi_trend != "STRONG BULLISH":
    signal = "WAIT"

if "PUT" in signal and oi_trend != "STRONG BEARISH":
    signal = "WAIT"

# ---------------- ENTRY ----------------
if st.session_state.trade is None and ("CALL" in signal or "PUT" in signal):

    strike = select_strike(price, signal)
    opt_type = "CE" if "CALL" in signal else "PE"
    option_price = get_option_price(strike, opt_type)

    st.session_state.trade = {
        "type": opt_type,
        "strike": strike,
        "entry": option_price,
        "sl": option_price - 20,
        "target": option_price + 40,
        "partial": False
    }

    send_telegram(f"ENTRY {opt_type} {strike} @ {option_price}")

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

# ---------------- UI ----------------
st.title("📊 AI Trading System PRO MAX")

st.metric("Price", round(price,2))
st.metric("EMA", round(ema,2))
st.metric("VWAP", round(vwap,2))

st.write(f"Trend: {trend15}")
st.write(f"Smart Money: {smart_money}")

st.subheader("📊 Confidence")
st.progress(score/100)

st.subheader(f"🚀 Signal: {signal}")

st.subheader("📊 OI Trend Intelligence")
st.write(f"OI Trend: {oi_trend}")

# AI Decision
st.subheader("🧠 AI Decision")
if "CALL" in signal or "PUT" in signal:
    st.success("ENTER TRADE")
elif signal=="NO TRADE":
    st.error("STAY OUT")

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

if st.session_state.trade:
    st.subheader("💼 Active Trade")
    st.write(st.session_state.trade)