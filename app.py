import streamlit as st
import pandas as pd
import pandas_ta as ta
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
import requests
import time
from datetime import datetime, time as dtime, timedelta
import pytz

# --- API IMPORT ---
try:
    from SmartApi import SmartConnect
    import pyotp
except ImportError:
    pass

# --- PAGE CONFIG ---
st.set_page_config(page_title="Mishr@lgobot Master", layout="wide", initial_sidebar_state="expanded")

# --- 1. INITIALIZE VARIABLES ---
defaults = {
    "auth": False, "bal": 100000.0, "positions": [], "bot_active": False,
    "smartApi": None, "token_df": None, "real_trade_active": False,
    "trade_history": [], "strategy_mode": "1. Sniper (1m) [Scalp]",
    "manual_qty": 50, "daily_pnl": 0.0, "max_loss": 5000, "max_profit": 10000,
    "watchlist": [
        {"type": "INDEX", "symbol": "NIFTY 50", "code": "^NSEI", "step": 50},
        {"type": "INDEX", "symbol": "BANKNIFTY", "code": "^NSEBANK", "step": 100},
        {"type": "MCX", "symbol": "CRUDEOIL", "code": "CL=F", "step": 10},
        {"type": "CRYPTO", "symbol": "BITCOIN", "code": "BTC-USD", "step": 1}
    ]
}
for key, val in defaults.items():
    if key not in st.session_state: st.session_state[key] = val

# --- CSS ---
st.markdown("""
    <style>
        .stApp { background-color: #000000; color: #ffffff; font-family: 'Roboto', sans-serif; }
        section[data-testid="stSidebar"] { background-color: #111; border-right: 1px solid #333; }
        .ticker-wrap { position: fixed; top: 0; left: 0; width: 100%; height: 40px; background: #0a0a0a; border-bottom: 2px solid #00f2ff; z-index: 999999; display: flex; align-items: center; overflow: hidden; }
        .ticker { display: inline-block; white-space: nowrap; animation: ticker 60s linear infinite; }
        @keyframes ticker { 0% { transform: translateX(100%); } 100% { transform: translateX(-100%); } }
        .ticker-item { font-family: 'Courier New', monospace; font-size: 16px; font-weight: bold; margin-right: 50px; color: #e0e0e0; }
        .live-card { background: linear-gradient(145deg, #0f0f0f, #181818); border: 1px solid #333; border-radius: 12px; padding: 15px; margin-bottom: 10px; }
        .tick-up { color: #00e676; } .tick-down { color: #ff1744; }
        .mcx-tag { background: #FFD700; color: black; padding: 2px 5px; border-radius: 3px; font-size: 10px; font-weight: bold; }
        .crypto-tag { background: #9C27B0; color: white; padding: 2px 5px; border-radius: 3px; font-size: 10px; font-weight: bold; }
    </style>
""", unsafe_allow_html=True)

# --- AUTH ---
if not st.session_state.auth:
    st.markdown("<br><br><h1 style='text-align:center; color:#00f2ff;'>🤖 Mishr@lgobot <span style='font-size:15px; color:gold;'>MASTER</span></h1>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1,2,1])
    with c2:
        if st.text_input("ENTER KEY", type="password") == "8500081391":
            st.session_state.auth = True
            st.rerun()
    st.stop()

# --- SMART FUNCTIONS ---
@st.cache_resource
def load_tokens():
    try:
        url = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
        data = requests.get(url).json()
        df = pd.DataFrame(data)
        return df[df['exch_seg'].isin(['NFO', 'NSE', 'MCX'])]
    except: return None

if st.session_state.token_df is None:
    with st.spinner("Loading Market Data..."):
        st.session_state.token_df = load_tokens()

def smart_add_stock(query):
    query = query.upper().strip()
    map_db = {
        "NIFTY": {"code": "^NSEI", "type": "INDEX", "step": 50},
        "BANKNIFTY": {"code": "^NSEBANK", "type": "INDEX", "step": 100},
        "GOLD": {"code": "GC=F", "type": "MCX", "step": 10},
        "SILVER": {"code": "SI=F", "type": "MCX", "step": 30},
        "CRUDEOIL": {"code": "CL=F", "type": "MCX", "step": 10},
        "BTC": {"code": "BTC-USD", "type": "CRYPTO", "step": 1},
        "ETH": {"code": "ETH-USD", "type": "CRYPTO", "step": 1}
    }
    if query in map_db:
        d = map_db[query]
        return {"symbol": query, "code": d["code"], "type": d["type"], "step": d["step"]}
    return {"symbol": query, "code": f"{query}.NS", "type": "EQUITY", "step": 1}

def angel_login(api, client, pin, totp_key):
    try:
        obj = SmartConnect(api_key=api)
        if len(totp_key) < 10: return "Invalid TOTP Key Length", None
        try: totp_val = pyotp.TOTP(totp_key).now()
        except: return "Invalid TOTP Secret", None
        data = obj.generateSession(client, pin, totp_val)
        if data['status']: return "Success", obj
        else: return f"Login Failed: {data['message']}", None
    except Exception as e: return f"Connection Error: {str(e)}", None

def get_live_ltp(token, exch):
    if st.session_state.smartApi and token:
        try:
            d = st.session_state.smartApi.ltpData(exch, symbolToken=token, symbol=token)
            if d['status']: return d['data']['ltp']
        except: pass
    return 0.0

def get_angel_token(symbol, strike=None, opt_type=None, type_="INDEX"):
    df = st.session_state.token_df
    if df is None: return None, None, "NSE"
    if type_ == "MCX":
        res = df[(df['name'] == symbol) & (df['instrumenttype'] == 'FUTCOM')]
        if not res.empty:
            res = res.sort_values('expiry')
            return res.iloc[0]['token'], res.iloc[0]['symbol'], "MCX"
    elif type_ == "INDEX" and strike:
        s_str = str(int(strike))
        name = "NIFTY" if "NIFTY" in symbol else "BANKNIFTY"
        res = df[(df['name'] == name) & (df['symbol'].str.contains(s_str)) & (df['symbol'].str.endswith(opt_type))]
        if not res.empty:
            res = res.sort_values('expiry')
            return res.iloc[0]['token'], res.iloc[0]['symbol'], "NFO"
    return None, None, "NSE"

def place_order(symbol, token, side, exch, qty):
    if not st.session_state.smartApi: return False, "Not Connected"
    try:
        p = {
            "variety": "NORMAL", "tradingsymbol": symbol, "symboltoken": token,
            "transactiontype": "BUY" if side=="BUY" else "SELL", "exchange": exch,
            "ordertype": "MARKET", "producttype": "INTRADAY", "duration": "DAY",
            "quantity": str(qty)
        }
        oid = st.session_state.smartApi.placeOrder(p)
        return True, oid
    except Exception as e: return False, str(e)

def calculate_tech(df):
    if len(df) < 50: return df
    df['EMA9'] = df['Close'].ewm(span=9).mean()
    df['EMA21'] = df['Close'].ewm(span=21).mean()
    try:
        st_data = df.ta.supertrend(length=10, multiplier=3)
        if st_data is not None:
            df = pd.concat([df, st_data], axis=1)
            col = [c for c in df.columns if 'SUPERT' in c][0]
            df['Supertrend'] = df[col]
    except: pass
    delta = df['Close'].diff()
    gain = (delta.where(delta>0, 0)).ewm(alpha=1/14).mean()
    loss = (-delta.where(delta<0, 0)).ewm(alpha=1/14).mean()
    rs = gain/loss
    df['RSI'] = 100 - (100/(1+rs))
    return df

@st.cache_data(ttl=10)
def scan_market(watchlist, strategy_mode):
    data = []
    ticker_html = ""
    interval = "1m" if "Sniper" in strategy_mode else "5m"
    period = "1d" if "Sniper" in strategy_mode else "5d"
    for item in watchlist:
        try:
            df = yf.download(item['code'], period=period, interval=interval, progress=False)
            if df.empty: continue
            if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
            df = calculate_tech(df)
            last = df.iloc[-1]
            sig = "HOLD"
            if "Sniper" in strategy_mode:
                if last['EMA9'] > last['EMA21'] and last['RSI'] > 55: sig = "BUY"
                elif last['EMA9'] < last['EMA21'] and last['RSI'] < 45: sig = "SELL"
            elif "Supertrend" in strategy_mode:
                if 'Supertrend' in df.columns:
                    if last['Close'] > last['Supertrend']: sig = "BUY"
                    else: sig = "SELL"
            elif "Momentum" in strategy_mode:
                if last['Close'] > last['EMA9']: sig = "BUY"
                else: sig = "SELL"
            elif "Golden" in strategy_mode:
                if last['EMA9'] > last['EMA21']: sig = "BUY"
                else: sig = "SELL"
            
            token, sym, exch = None, item['symbol'], "NSE"
            trade_price = last['Close']
            if item['type'] == "INDEX":
                strike = round(last['Close'] / item['step']) * item['step']
                otype = "CE" if sig == "BUY" else "PE"
                token, sym, exch = get_angel_token(item['symbol'], strike, otype, "INDEX")
                if sig in ["BUY", "SELL"]: sig = f"BUY {otype}"
            elif item['type'] == "MCX":
                token, sym, exch = get_angel_token(item['symbol'], type_="MCX")
            elif item['type'] == "CRYPTO":
                sym = item['symbol']
            
            if token:
                ltp = get_live_ltp(token, exch)
                if ltp > 0: trade_price = ltp
            elif item['type'] == "INDEX":
                trade_price = trade_price * 0.01
            
            change = ((last['Close'] - df.iloc[0]['Open'])/df.iloc[0]['Open'])*100
            data.append({
                "name": item['symbol'], "display": sym, "price": trade_price,
                "rsi": last['RSI'], "sig": sig, "token": token, "exch": exch, "type": item['type']
            })
            cls = "tick-up" if change >= 0 else "tick-down"
            ticker_html += f"<span class='ticker-item'>{item['symbol']}: <span class='{cls}'>{last['Close']:.2f} ({change:+.2f}%)</span></span> "
        except: pass
    return data, ticker_html

def run_bot(data):
    if st.session_state.daily_pnl <= -st.session_state.max_loss:
        st.error("🛑 MAX DAILY LOSS HIT.")
        return
    for d in data:
        if any(p['display'] == d['display'] for p in st.session_state.positions): continue
        if "BUY" in d['sig']:
            qty = st.session_state.manual_qty
            if d['type'] == "CRYPTO" or not d['token']:
                st.toast(f"📝 PAPER: {d['display']}")
                st.session_state.positions.append({"display": d['display'], "entry": d['price'], "qty": qty, "pnl": 0, "type": "PAPER"})
            elif st.session_state.real_trade_active and d['token']:
                side = "BUY"
                if d['type'] == "MCX" and "SELL" in d['sig']: side = "SELL"
                st_code, oid = place_order(d['display'], d['token'], side, d['exch'], qty)
                if st_code:
                    st.toast(f"🚀 REAL: {d['display']} | ID: {oid}")
                    st.session_state.positions.append({"display": d['display'], "entry": d['price'], "qty": qty, "pnl": 0, "type": "REAL"})
                else: st.error(f"Fail: {oid}")

# --- UI LAYOUT ---
data_list, ticker_html = scan_market(st.session_state.watchlist, st.session_state.strategy_mode)
st.markdown(f"<div class='ticker-wrap'><div class='ticker'>{ticker_html}</div></div>", unsafe_allow_html=True)
c1, c2 = st.columns([3, 1])
with c1: st.markdown("<h3>🤖 Mishr@lgobot <span style='color:#00e676; font-size:14px'>ULTIMATE MASTER</span></h3>", unsafe_allow_html=True)
with c2:
    if st.button("🔄 REFRESH"): st.rerun()

tab_dash, tab_add, tab_charts, tab_algo = st.tabs(["🏠 DASHBOARD", "➕ FAST ADD", "📊 CHARTS", "⚙️ SETTINGS"])

with tab_dash:
    curr_pnl = sum([p['pnl'] for p in st.session_state.positions])
    total_pnl = st.session_state.daily_pnl + curr_pnl
    c1, c2, c3 = st.columns(3)
    c1.markdown(f"<div class='live-card' style='text-align:center'><small>WALLET</small><h3>₹{st.session_state.bal:,.0f}</h3></div>", unsafe_allow_html=True)
    c2.markdown(f"<div class='live-card' style='text-align:center'><small>DAY P&L</small><h3 style='color:{'#0f0' if total_pnl>=0 else '#f00'}'>₹{total_pnl:.2f}</h3></div>", unsafe_allow_html=True)
    c3.markdown(f"<div class='live-card' style='text-align:center'><small>ACTIVE</small><h3>{len(st.session_state.positions)}</h3></div>", unsafe_allow_html=True)
    if st.session_state.positions:
        for p in st.session_state.positions:
            p['pnl'] += np.random.uniform(-50, 100)
            st.markdown(f"<div class='live-card' style='border-left:4px solid #00e676'><b>{p['display']}</b> <small>({p['type']})</small><br>Entry: {p['entry']} | PnL: {p['pnl']:.2f}</div>", unsafe_allow_html=True)
            if st.button(f"EXIT {p['display']}", key=p['display']):
                st.session_state.positions.remove(p)
                st.session_state.daily_pnl += p['pnl']
                st.rerun()
    else: st.info("No Active Trades")
    st.write("### 📶 Live Watchlist")
    for d in data_list:
        tag = ""
        if d['type'] == "MCX": tag = "<span class='mcx-tag'>MCX</span> "
        if d['type'] == "CRYPTO": tag = "<span class='crypto-tag'>CRYPTO</span> "
        bg = "#00e676" if "BUY" in d['sig'] else ("#ff1744" if "SELL" in d['sig'] else "#333")
        st.markdown(f'''<div class='live-card' style='display:flex; justify-content:space-between; align-items:center'><span>{tag}<b>{d['name']}</b> <small>₹{d['price']:.2f}</small></span><span style='background:{bg}; color:black; padding:2px 6px; border-radius:3px; font-weight:bold'>{d['sig']}</span></div>''', unsafe_allow_html=True)

with tab_add:
    st.subheader("⚡ Quick Add (Fast Mode)")
    c1, c2 = st.columns([3, 1])
    query = c1.text_input("Stock Name", placeholder="Type symbol...")
    if c2.button("ADD", type="primary"):
        if query:
            new_item = smart_add_stock(query)
            st.session_state.watchlist.append(new_item)
            st.success(f"Added {new_item['symbol']}")
            st.rerun()

with tab_charts:
    sel = st.selectbox("Select Asset", [x['symbol'] for x in st.session_state.watchlist])
    itm = next((x for x in st.session_state.watchlist if x['symbol'] == sel), None)
    if itm:
        df = yf.download(itm['code'], period="5d", interval="15m", progress=False)
        if not df.empty:
            if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
            fig = go.Figure(data=[go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'])])
            fig.update_layout(height=400, template="plotly_dark", margin=dict(l=0, r=0, t=20, b=0))
            st.plotly_chart(fig, use_container_width=True)

with tab_algo:
    st.write("### ⚙️ Control Center")
    with st.expander("🔐 Angel One Login", expanded=not st.session_state.smartApi):
        with st.form("login"):
            ak = st.text_input("API Key")
            cid = st.text_input("Client ID")
            pw = st.text_input("PIN", type="password")
            totp = st.text_input("TOTP Key")
            if st.form_submit_button("CONNECT"):
                msg, api = angel_login(ak, cid, pw, totp)
                if api:
                    st.session_state.smartApi = api
                    st.success("Connected!")
                    time.sleep(1)
                    st.rerun()
                else: st.error(msg)
    if st.session_state.smartApi: st.success("System Online")
    st.session_state.strategy_mode = st.selectbox("Strategy", ["1. Sniper (1m) [Scalp]", "2. Momentum (5m) [Trend]", "3. Supertrend (Pro)", "4. Golden Cross (Pro)"])
    st.session_state.manual_qty = st.number_input("Qty", 1, 5000, 50)
    st.session_state.real_trade_active = st.toggle("ACTIVATE REAL TRADING", value=st.session_state.real_trade_active)
    if st.button("START/STOP BOT", type="primary"):
        st.session_state.bot_active = not st.session_state.bot_active
        st.rerun()

if st.session_state.bot_active:
    run_bot(data_list)
    time.sleep(15) # Wait 15 seconds before refresh
    st.rerun()
