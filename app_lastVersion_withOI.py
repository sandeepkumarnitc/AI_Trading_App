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

st.set_page_config(layout="wide", page_title="AI Trading System")

# ---------------- SESSION ----------------
if "trades" not in st.session_state:
    st.session_state.trades = []
if "active_trade" not in st.session_state:
    st.session_state.active_trade = None

st.title("📊 AI Trading System (Pro)")
st.caption("MTF + VWAP + Volume + Smart Money + Paper Trading")

# ---------------- DATA ----------------
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
    df["EMA_44"] = df["close"].ewm(span=44).mean()
    return df

@st.cache_data
def get_instruments():
    return pd.DataFrame(kite.instruments("NFO"))

# ---------------- FETCH ----------------
df5 = get_data("5minute")
df15 = get_data("15minute")

price = df5["close"].iloc[-1]
ema5 = df5["EMA_44"].iloc[-1]
ema15 = df15["EMA_44"].iloc[-1]
price15 = df15["close"].iloc[-1]

# ---------------- VWAP FUTURES ----------------
inst = get_instruments()

fut = inst[(inst["name"]=="NIFTY") & (inst["instrument_type"]=="FUT")]
expiry = fut["expiry"].min()
fut_token = int(fut[fut["expiry"]==expiry].iloc[0]["instrument_token"])

df_fut = pd.DataFrame(kite.historical_data(
    fut_token,
    datetime.datetime.now()-datetime.timedelta(days=2),
    datetime.datetime.now(),
    "5minute"
))

df_fut["date"] = pd.to_datetime(df_fut["date"])
today = df_fut["date"].dt.date.iloc[-1]
df_today = df_fut[df_fut["date"].dt.date == today]

df_today["cum_vol"] = df_today["volume"].cumsum()
df_today["cum_val"] = (df_today["close"]*df_today["volume"]).cumsum()
df_today["VWAP"] = df_today["cum_val"]/df_today["cum_vol"]

vwap = df_today["VWAP"].iloc[-1]

# ---------------- STRUCTURE ----------------
recent_high = df5["high"].rolling(10).max().iloc[-2]
recent_low = df5["low"].rolling(10).min().iloc[-2]

# ---------------- TREND ----------------
trend15 = "BULLISH" if price15 > ema15 else "BEARISH"

# ---------------- CHOP ----------------
last5_range = df5["high"].iloc[-5:].max() - df5["low"].iloc[-5:].min()
chop = last5_range < 40

# ---------------- VOLUME ----------------
df5["vol_ma"] = df5["volume"].rolling(20).mean()
volume_spike = df5["volume"].iloc[-1] > 1.5 * df5["vol_ma"].iloc[-1]

# ---------------- CANDLE ----------------
last = df5.iloc[-1]
body = abs(last["close"] - last["open"])
range_candle = last["high"] - last["low"]

body_ratio = body / range_candle if range_candle != 0 else 0
strong_candle = body_ratio > 0.6

# ---------------- BREAKOUT ----------------
breakout_up = last["close"] > recent_high and strong_candle
breakout_down = last["close"] < recent_low and strong_candle

# ---------------- FAKE ----------------
upper_wick = last["high"] - max(last["open"], last["close"])
lower_wick = min(last["open"], last["close"]) - last["low"]

fake_up = upper_wick > body
fake_down = lower_wick > body

# ---------------- OI + PCR ----------------
def get_pcr(opt_df):
    ce_oi = 0
    pe_oi = 0

    symbols = ["NFO:" + s for s in opt_df["tradingsymbol"].tolist()]

    try:
        quotes = kite.quote(symbols)

        for sym in symbols:
            data = quotes.get(sym, {})

            oi = data.get("oi", 0)

            if "CE" in sym:
                ce_oi += oi
            elif "PE" in sym:
                pe_oi += oi

        if ce_oi == 0:
            return 1

        return pe_oi / ce_oi

    except:
        return 1

#opt_all = inst[(inst["name"]=="NIFTY") & (inst["instrument_type"].isin(["CE","PE"]))]
atm = round(price/50)*50
strikes = [atm-200, atm-100, atm, atm+100, atm+200]

opt_all = inst[
    (inst["name"]=="NIFTY") &
    (inst["instrument_type"].isin(["CE","PE"])) &
    (inst["strike"].isin(strikes))
]

expiry = opt_all["expiry"].min()
opt_all = opt_all[opt_all["expiry"] == expiry]
expiry = opt_all["expiry"].min()
opt_all = opt_all[opt_all["expiry"] == expiry]

pcr = get_pcr(opt_all) if opt_all is not None else 1

# Smart money bias
if pcr > 1.2:
    smart_bias = "BULLISH"
elif pcr < 0.8:
    smart_bias = "BEARISH"
else:
    smart_bias = "NEUTRAL"

# ---------------- SIGNAL ----------------
signal = "WAIT"

if chop:
    signal = "NO TRADE"

elif trend15 == "BULLISH" and smart_bias != "BEARISH":
    if breakout_up and volume_spike and not fake_up:
        signal = "BUY CALL"

elif trend15 == "BEARISH" and smart_bias != "BULLISH":
    if breakout_down and volume_spike and not fake_down:
        signal = "BUY PUT"

# ---------------- OPTIONS ----------------
atm = round(price/50)*50
strikes = [atm-100, atm-50, atm, atm+50, atm+100]

opt_df = opt_all[opt_all["strike"].isin(strikes)]

def get_price(sym):
    try:
        return kite.ltp("NFO:"+sym)["NFO:"+sym]["last_price"]
    except:
        return None

opt_df["price"] = opt_df["tradingsymbol"].apply(get_price)

def pick(signal):
    if "CALL" in signal:
        return opt_df[opt_df["instrument_type"]=="CE"].iloc[2]
    elif "PUT" in signal:
        return opt_df[opt_df["instrument_type"]=="PE"].iloc[2]
    return None

selected = pick(signal)

# ---------------- UI ----------------
col1, col2, col3 = st.columns(3)
col1.metric("Price", round(price,2))
col2.metric("EMA", round(ema5,2))
col3.metric("VWAP", round(vwap,2))

st.write(f"Trend15: {trend15} | PCR: {round(pcr,2)} | Smart Bias: {smart_bias}")
st.write(f"Volume Spike: {volume_spike} | Strong Candle: {strong_candle} | Chop: {chop}")

st.subheader(f"🚀 Signal: {signal}")

# ---------------- PAPER TRADE ----------------
if selected is not None and "WAIT" not in signal:

    st.write(selected["tradingsymbol"], selected["price"])

    entry = st.number_input("Entry Price", value=float(selected["price"]))
    sl = entry * 0.88
    target = entry * 1.4

    if st.button("Enter Trade"):
        st.session_state.active_trade = {
            "symbol": selected["tradingsymbol"],
            "entry": entry,
            "sl": sl,
            "target": target,
            "qty": 75,
            "status": "OPEN",
            "pnl": 0,
            "setup": signal
        }

# ---------------- ACTIVE ----------------
trade = st.session_state.active_trade

if trade and trade["status"] == "OPEN":

    ltp = get_price(trade["symbol"])

    if ltp:
        pnl = (ltp - trade["entry"]) * trade["qty"]
        trade["pnl"] = pnl

        st.write(f"LTP: {ltp} | PnL: {round(pnl,2)}")

        if ltp <= trade["sl"]:
            trade["status"] = "SL HIT"
        elif ltp >= trade["target"]:
            trade["status"] = "TARGET HIT"

        if st.button("Exit Trade"):
            trade["status"] = "MANUAL EXIT"

        if trade["status"] != "OPEN":
            st.session_state.trades.append(trade.copy())
            st.session_state.active_trade = None

# ---------------- HISTORY ----------------
st.subheader("📒 Trade History")

if st.session_state.trades:
    df_trades = pd.DataFrame(st.session_state.trades)
    st.dataframe(df_trades)

    st.write("Total PnL:", round(df_trades["pnl"].sum(),2))
    st.write("Win Rate:", len(df_trades[df_trades["pnl"]>0])/len(df_trades))
else:
    st.info("No trades yet")