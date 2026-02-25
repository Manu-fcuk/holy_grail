import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import sqlite3
import os
import requests
import time
import feedparser
from datetime import datetime, timedelta
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import io

# --- 1. SETUP & THEME ---
st.set_page_config(page_title="RS Momentum Terminal", layout="wide")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "market_data.db")

st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    .stMetric { background-color: #161b22; padding: 15px; border-radius: 10px; border: 1px solid #30363d; }
    .stTabs [data-baseweb="tab-list"] { gap: 10px; }
    .stTabs [data-baseweb="tab"] { background-color: #161b22; border-radius: 5px; color: white; padding: 10px 18px; }
    .stTabs [aria-selected="true"] { background-color: #238636; }
    div[data-testid="stExpander"] { border: 1px solid #30363d; background-color: #0e1117; }
    .status-box { padding: 22px; border-radius: 12px; text-align: center; font-weight: bold; font-size: 24px; margin-bottom: 10px; border: 2px solid #30363d; }
    .intel-box { padding: 15px; border-radius: 8px; background-color: #1c2128; border-left: 5px solid #238636; margin-bottom: 20px; min-height: 200px; }
    .outlook-card { background-color: #1c2128; padding: 20px; border-radius: 10px; border-top: 3px solid #388bfd; margin-top: 10px; line-height: 1.7; }
    .calendar-event { padding: 8px 4px; border-bottom: 1px solid #30363d; font-size: 14px; }
    .disclaimer { font-size: 13px; color: #8b949e; margin-top: 50px; border: 1px solid #da3633; padding: 20px; border-radius: 10px; background-color: #211111; line-height: 1.6; }
    .checklist-card { padding: 16px 20px; border-radius: 10px; background-color: #161b22; border: 1px solid #30363d; margin-bottom: 14px; }
    .checklist-title { font-size: 1.1em; font-weight: bold; margin-bottom: 4px; }
    .checklist-subtitle { font-size: 0.82em; color: #8b949e; }
    .check-banner-green { background: linear-gradient(90deg, #0d2e1a, #1a4a2e); border: 1px solid #238636; border-radius: 10px; padding: 16px 22px; text-align: center; font-size: 1.05em; font-weight: bold; color: #3fb950; margin-bottom: 20px; }
    .check-banner-yellow { background: linear-gradient(90deg, #2e2900, #4a3d00); border: 1px solid #b18c00; border-radius: 10px; padding: 16px 22px; text-align: center; font-size: 1.05em; font-weight: bold; color: #e3b341; margin-bottom: 20px; }
    .check-banner-red { background: linear-gradient(90deg, #2e0d0d, #4a1a1a); border: 1px solid #da3633; border-radius: 10px; padding: 16px 22px; text-align: center; font-size: 1.05em; font-weight: bold; color: #f85149; margin-bottom: 20px; }
    .news-card { background:#161b22; border-left:4px solid #388bfd; padding:10px 14px; margin-bottom:8px; border-radius:6px; }
    .earnings-beat { color:#3fb950; font-weight:bold; }
    .earnings-miss { color:#f85149; font-weight:bold; }
    .earnings-pending { color:#e3b341; font-weight:bold; }
    .phase-card { background:#1c2128; border-radius:10px; padding:18px; margin-bottom:12px; border: 1px solid #30363d; }
    .bt-info-card { background:#161b22; border-radius:8px; padding:16px; border-left:4px solid #f1e05a; margin-bottom:14px; line-height:1.7; }
    </style>
""", unsafe_allow_html=True)

# ── 2. CORE FUNCTIONS ─────────────────────────────────────────────────────────

def get_db_data():
    if not os.path.exists(DB_PATH):
        return None, None
    try:
        conn = sqlite3.connect(DB_PATH)
        prices   = pd.read_sql("SELECT * FROM prices", conn, index_col='Date', parse_dates=['Date'])
        companies = pd.read_sql("SELECT * FROM companies", conn)
        conn.close()
        return prices, companies
    except:
        return None, None

@st.cache_data(ttl=86400)
def get_company_static_info(ticker):
    _, companies = get_db_data()
    if companies is not None:
        match = companies[companies['Symbol'] == ticker]
        if not match.empty:
            return {"Name": match.iloc[0]['Security'], "Sector": match.iloc[0]['GICS Sector']}
    try:
        inf = yf.Ticker(ticker).info
        return {"Name": inf.get('longName', ticker), "Sector": inf.get('sector', 'N/A')}
    except:
        return {"Name": ticker, "Sector": "N/A"}

def calc_rs_stable(prices, bm_prices):
    combined = pd.concat([prices, bm_prices], axis=1).ffill().dropna()
    if combined.empty: return pd.Series()
    combined.columns = ['Asset', 'BM']
    ratio = combined['Asset'] / combined['BM'].replace(0, np.nan)
    return (ratio / ratio.rolling(window=50).mean()) - 1

def calc_rsi(prices, window=14):
    if len(prices) < window: return pd.Series([50]*len(prices))
    delta = prices.diff()
    gain  = (delta.where(delta > 0, 0)).rolling(window).mean()
    loss  = (-delta.where(delta < 0, 0)).rolling(window).mean()
    return 100 - (100 / (1 + (gain / loss.replace(0, np.nan)).ffill()))

def get_sp500_list():
    _, companies = get_db_data()
    if companies is not None:
        return companies['Symbol'].tolist()
    return fetch_sp500_wiki()

@st.cache_data(ttl=3600)
def fetch_sp500_wiki():
    try:
        html = requests.get('https://en.wikipedia.org/wiki/List_of_S%26P_500_companies',
                            headers={'User-Agent':'Mozilla/5.0'}).text
        df = pd.read_html(io.StringIO(html))[0]
        return [t.replace('.', '-') for t in df['Symbol'].tolist()]
    except:
        return ["NVDA","AAPL","MSFT","GOOGL","AMZN","META"]

def get_market_intelligence(bm_prices):
    if len(bm_prices) < 200: return "N/A","N/A","N/A","","Neutral",50
    sma50  = bm_prices.rolling(50).mean().iloc[-1]
    sma200 = bm_prices.rolling(200).mean().iloc[-1]
    curr   = bm_prices.iloc[-1]
    if curr > sma50 and sma50 > sma200:
        ph, adv = "Markup 🚀 (Phase 2)", "Starker Bullen-Trend aktiv. Vollgasposition in Leading Stocks mit RS > Benchmark. Kein Contrarian – nur die Besten kaufen."
    elif curr < sma50 and curr > sma200:
        ph, adv = "Distribution ⚠️ (Phase 3)", "Markt verliert Schwung. Volatilität steigt. Stops eng ziehen. Neue Positionen nur noch mit stark überzeugenden RS-Signalen."
    elif curr < sma50 and curr < sma200:
        ph, adv = "Markdown 🔴 (Phase 4)", "Bestätigter Bärenmarkt. Kapitalschutz hat Priorität. 80% Cash-Quote. Short-ETFs oder Cash. Keine neuen Long-Positionen."
    else:
        ph, adv = "Accumulation 📈 (Phase 1)", "Mögliche Bodenbildung. Selektiv akkumulieren. RS-Ausbrüche neuer Leader beobachten. Noch keine Vollgas-Position."
    m = datetime.now().month
    seasonal_map = {
        1:  ("Januar ❄️",  "Bullish",   "Jahresanfang meist stark. New-Money-Effekt treibt Aktien. Saisonaler Einstieg für Momentum-Strategie."),
        2:  ("Februar 🌨️", "Volatil",   "Häufig Konsolidierung nach dem Januar-Rally. Gewinnmitnahmen möglich. Stops prüfen."),
        3:  ("März 🌱",    "Bullish",   "Frühjahrs-Rally häufig. Gute Einstiegschancen nach Februar-Korrektur."),
        4:  ("April 🌸",   "Sehr Stark","Historisch einer der stärksten Monate. 'Best 6 Months' April–September beginnt."),
        5:  ("Mai ☀️",     "Vorsicht",  "'Sell in May and go away' – historische Schwächephase beginnt. Stops eng halten."),
        6:  ("Juni 🌞",    "Neutral",   "Unbeständig. Oft seitwärts bis schwach. Positionsgrössen reduzieren."),
        7:  ("Juli 🏖️",    "Bullish",   "Erholung nach Sommer-Dip häufig. Earnings Season treibt Leader."),
        8:  ("August 🌊",  "Schwach",   "Volumen niedrig, Flash-Crashs möglich. Defensiv bleiben."),
        9:  ("September 🍂","Schwach",  "Historisch schwächster Monat des Jahres. Risiko reduzieren."),
        10: ("Oktober 🎃", "Volatil",   "Oft Tiefstkurse und Umkehrpunkte. Fundament für Q4-Rally legen."),
        11: ("November 🦃","Sehr Stark","Q4-Rally beginnt. 'Best 6 Months' Periode. Hohe Momentum-Renditen historisch."),
        12: ("Dezember 🎄","Bullish",   "Weihnachts-Rally, Window Dressing der Fonds. Jahr-End-Effekt positiv."),
    }
    s_name, s_mood, s_detail = seasonal_map.get(m, ("Neutral","Neutral","Kein spezifischer saisonaler Faktor."))
    rsi_val = calc_rsi(bm_prices).iloc[-1]
    if rsi_val >= 75:
        sent, sent_desc = "Extreme Gier 🔥🔥", f"RSI {rsi_val:.0f} – Markt stark überkauft. Gewinne sichern, Stops nachziehen. Korrekturgefahr erhöht."
    elif rsi_val >= 65:
        sent, sent_desc = "Gier 🔥", f"RSI {rsi_val:.0f} – Bullische Dynamik intakt aber überhitzt. Selektiv bleiben, keine aggressiven Neueinstiege."
    elif rsi_val <= 25:
        sent, sent_desc = "Extreme Angst 😱", f"RSI {rsi_val:.0f} – Kapitulation möglich. Konträr akkumulieren. Turnaround-Kandidaten scannen."
    elif rsi_val <= 35:
        sent, sent_desc = "Angst 😨", f"RSI {rsi_val:.0f} – Überverkauft. Antizyklische Einstiegsgelegenheiten entstehen. Geduld zahlt sich aus."
    else:
        sent, sent_desc = "Neutral ⚖️", f"RSI {rsi_val:.0f} – Gesundes Gleichgewicht. Momentum-System normal weiter betreiben."
    return ph, adv, s_name, s_detail, sent, rsi_val, s_mood, sent_desc

@st.cache_data(ttl=3600)
def get_market_checklist(bm_prices_full_tuple):
    bm_prices_full = pd.Series(bm_prices_full_tuple[1], index=pd.to_datetime(bm_prices_full_tuple[0]))
    results = {}
    try:
        if len(bm_prices_full) >= 200:
            sma200 = bm_prices_full.rolling(200).mean().iloc[-1]
            curr   = bm_prices_full.iloc[-1]
            results['regime'] = {"label":"Regime Check","desc":f"Kurs: {curr:.0f} | SMA 200: {sma200:.0f}","pass":bool(curr>sma200)}
        else:
            results['regime'] = {"label":"Regime Check","desc":"Nicht genug Daten","pass":None}
    except:
        results['regime'] = {"label":"Regime Check","desc":"Fehler","pass":None}
    try:
        db_prices, _ = get_db_data()
        sp500_tickers = get_sp500_list()
        if db_prices is not None:
            valid = [c for c in db_prices.columns if c in sp500_tickers]
            if len(valid) >= 50:
                recent = db_prices[valid].ffill()
                abv = sum(1 for c in valid if len(recent[c].dropna())>=50 and recent[c].dropna().iloc[-1] > recent[c].dropna().rolling(50).mean().iloc[-1])
                total = sum(1 for c in valid if len(recent[c].dropna())>=50)
                pct = abv/total*100 if total>0 else 0
                results['breadth'] = {"label":"Breadth Check","desc":f"{abv}/{total} Aktien ({pct:.1f}%)","pass":bool(pct>50)}
            else:
                results['breadth'] = {"label":"Breadth Check","desc":"Nicht genug Ticker","pass":None}
        else:
            results['breadth'] = {"label":"Breadth Check","desc":"DB nicht verfügbar","pass":None}
    except Exception as e:
        results['breadth'] = {"label":"Breadth Check","desc":str(e)[:60],"pass":None}
    try:
        vix = yf.download("^VIX", period="5d", progress=False, auto_adjust=True)['Close']
        if isinstance(vix, pd.DataFrame): vix = vix.iloc[:,0]
        v = float(vix.dropna().iloc[-1])
        results['vix'] = {"label":"VIX Check","desc":f"VIX aktuell: {v:.2f}","pass":bool(v<25)}
    except:
        results['vix'] = {"label":"VIX Check","desc":"Nicht ladbar","pass":None}
    try:
        if len(bm_prices_full) >= 252:
            r = (bm_prices_full.iloc[-1]/bm_prices_full.iloc[-252]-1)*100
            results['abs_mom'] = {"label":"Absolute Momentum","desc":f"12M-Rendite: {r:+.2f}%","pass":bool(r>0)}
        else:
            results['abs_mom'] = {"label":"Absolute Momentum","desc":"Nicht genug Daten","pass":None}
    except:
        results['abs_mom'] = {"label":"Absolute Momentum","desc":"Fehler","pass":None}
    return results

@st.cache_data(ttl=1800)
def get_earnings_calendar(tickers):
    rows = []
    for t in tickers:
        try:
            tk = yf.Ticker(t)
            info = tk.info or {}
            
            # --- Get Earnings Date ---
            earn_date = "N/A"
            try:
                cal = tk.calendar
                if isinstance(cal, dict):
                    ed = cal.get('Earnings Date')
                    if ed:
                        earn_date = str(ed[0])[:10] if isinstance(ed, (list, tuple)) else str(ed)[:10]
                elif isinstance(cal, pd.DataFrame) and not cal.empty:
                    if 'Earnings Date' in cal.index:
                        v = cal.loc['Earnings Date']
                        earn_date = str(v.iloc[0])[:10] if hasattr(v, 'iloc') else str(v)[:10]
            except:
                pass
                
            if earn_date == "N/A":
                try:
                    ed_df = tk.earnings_dates
                    if ed_df is not None and not ed_df.empty:
                        # Find closest future date
                        future = ed_df[ed_df.index >= pd.Timestamp.now(tz='UTC')]
                        if not future.empty:
                            earn_date = str(future.index[0])[:10]
                        else:
                            earn_date = str(ed_df.index[0])[:10]
                except:
                    pass

            # --- Get Estimates ---
            eps_est = info.get('epsForwardQuarter') or info.get('forwardEps')
            rev_est = info.get('revenueEstimate') or info.get('totalRevenue')
            
            # --- Last Quarter Performance ---
            beat_str = "N/A"
            try:
                # Try earnings_dates for reported vs estimate
                ed_df = tk.earnings_dates
                if ed_df is not None and not ed_df.empty:
                    # Look for the last row with reported EPS
                    past = ed_df[ed_df['Reported EPS'].notna()].sort_index(ascending=False) if 'Reported EPS' in ed_df.columns else pd.DataFrame()
                    if not past.empty:
                        last_q = past.iloc[0]
                        actual = last_q.get('Reported EPS')
                        estimate = last_q.get('EPS Estimate')
                        if pd.notna(actual) and pd.notna(estimate) and estimate != 0:
                            surprise = (actual - estimate) / abs(estimate) * 100
                            beat_str = f"Beat +{surprise:.1f}%" if actual >= estimate else f"Miss {surprise:.1f}%"
            except:
                pass

            rows.append({
                "Ticker": t,
                "Name": info.get('shortName', t),
                "Earnings Date": earn_date,
                "EPS Est.": f"${eps_est:.2f}" if pd.notna(eps_est) else "N/A",
                "Rev Est.": f"${rev_est/1e9:.1f}B" if pd.notna(rev_est) else "N/A",
                "Last Q Beat/Miss": beat_str,
            })
        except Exception:
            rows.append({"Ticker":t,"Name":t,"Earnings Date":"N/A","EPS Est.":"N/A","Rev Est.":"N/A","Last Q Beat/Miss":"N/A"})
    return pd.DataFrame(rows)

@st.cache_data(ttl=900)
def get_market_news_feed():
    articles = []
    feeds = [
        "https://feeds.finance.yahoo.com/rss/2.0/headline?s=^GSPC&region=US&lang=en-US",
        "https://finance.yahoo.com/news/rssindex",
        "https://feeds.a.dj.com/rss/RSSMarketsMain.xml",
    ]
    for url in feeds:
        try:
            feed = feedparser.parse(url)
            for e in feed.entries[:8]:
                title = e.get('title','').strip()
                if title:
                    articles.append({"title":title, "link":e.get('link','#'), "published":e.get('published','')[:20]})
        except:
            pass
    return articles[:20]

ECONOMIC_EVENTS_2025_2026 = [
    {"date":"2026-02-26","event":"Konsumentenvertrauen (CB)","impact":"🟡 Mittel"},
    {"date":"2026-02-28","event":"PCE Preisindex (FED-Favorit)","impact":"🔴 Hoch"},
    {"date":"2026-03-05","event":"Dienstleistungssektor PMI (ISM)","impact":"🟡 Mittel"},
    {"date":"2026-03-07","event":"Arbeitsmarktbericht (NFP)","impact":"🔴 Hoch"},
    {"date":"2026-03-12","event":"CPI Inflationsdaten USA","impact":"🔴 Hoch"},
    {"date":"2026-03-18","event":"Produzentenpreise (PPI)","impact":"🟡 Mittel"},
    {"date":"2026-03-18","event":"FOMC Meeting Beginn","impact":"🔴 Hoch"},
    {"date":"2026-03-19","event":"FOMC Zinsentscheid + Pressekonfernz","impact":"🔴 Hoch"},
    {"date":"2026-03-28","event":"PCE Preisindex (FED-Favorit)","impact":"🔴 Hoch"},
    {"date":"2026-04-02","event":"Arbeitsmarktbericht (NFP)","impact":"🔴 Hoch"},
    {"date":"2026-04-10","event":"CPI Inflationsdaten USA","impact":"🔴 Hoch"},
    {"date":"2026-04-15","event":"Retail Sales","impact":"🟡 Mittel"},
    {"date":"2026-04-28","event":"PCE + BIP erste Schätzung Q1","impact":"🔴 Hoch"},
    {"date":"2026-04-29","event":"FOMC Meeting Beginn","impact":"🔴 Hoch"},
    {"date":"2026-04-30","event":"FOMC Zinsentscheid","impact":"🔴 Hoch"},
    {"date":"2026-05-08","event":"Arbeitsmarktbericht (NFP)","impact":"🔴 Hoch"},
    {"date":"2026-06-10","event":"FOMC Zinsentscheid","impact":"🔴 Hoch"},
]

def get_upcoming_events(days=45):
    today = datetime.now().date()
    cutoff = today + timedelta(days=days)
    upcoming = []
    for e in ECONOMIC_EVENTS_2025_2026:
        try:
            d = datetime.strptime(e['date'],"%Y-%m-%d").date()
            if today <= d <= cutoff:
                delta = (d - today).days
                upcoming.append({**e, "days_until": delta})
        except:
            pass
    return sorted(upcoming, key=lambda x: x['date'])

# ── 3. SIDEBAR ─────────────────────────────────────────────────────────────────
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2620/2620611.png", width=60)
    st.title("RS Momentum v1.0")
    u_input = st.text_area("Watchlist Tickers:", value="GOOG, AAPL, AMZN, WMT, T, META, NVDA, TSLA, MSFT, LLY, GE, PYPL, SNAP, ASML, PLTR", height=150)
    portfolio_list = [x.strip().upper() for x in u_input.split(",") if x.strip()]
    st.divider()
    bt_s_year     = st.number_input("Backtest Start", 2015, 2024, 2021)
    bt_e_year     = st.number_input("Backtest End",   2016, 2026, 2025)
    bt_univ_choice = st.radio("Backtest Universe", ["Watchlist","S&P 500 Index"])
    hold_mo_val   = st.select_slider("Holding (Mo)", options=[1,2,3,4,6], value=1)
    sl_input_val  = st.slider("Stop Loss %", 5, 30, 15)
    if st.button("🔄 Update DB Now"):
        with st.status("Updating Local Database..."):
            import subprocess
            subprocess.run(["python3", os.path.join(BASE_DIR,"db_updater.py")])
            st.success("Database Updated!")

# ── 4. DATA FETCH ──────────────────────────────────────────────────────────────
with st.spinner("Synchronisiere Terminal-Daten..."):
    db_prices, _ = get_db_data()
    if db_prices is not None and "^GSPC" in db_prices.columns:
        bm_prices_full = db_prices["^GSPC"].dropna()
    else:
        bm_prices_full = yf.download("^GSPC", period="5y", progress=False, auto_adjust=True)['Close']
        if isinstance(bm_prices_full, pd.DataFrame): bm_prices_full = bm_prices_full.iloc[:,0]

    missing_from_db  = [t for t in portfolio_list if db_prices is None or t not in db_prices.columns]
    port_db          = db_prices[[t for t in portfolio_list if db_prices is not None and t in db_prices.columns]] if db_prices is not None else pd.DataFrame()
    if missing_from_db:
        port_yf = yf.download(missing_from_db, period="4y", progress=False, auto_adjust=True)['Close']
        live_port_prices = pd.concat([port_db, port_yf], axis=1).ffill()
    else:
        live_port_prices = port_db.ffill()
    if isinstance(live_port_prices, pd.DataFrame) and isinstance(live_port_prices.columns, pd.MultiIndex):
        live_port_prices.columns = live_port_prices.columns.get_level_values(0)

# ── 5. HEADER ─────────────────────────────────────────────────────────────────
result = get_market_intelligence(bm_prices_full)
m_ph, m_adv, s_name, s_detail, m_sent, rsi_val, s_mood, sent_desc = result

m_bull = False
if not bm_prices_full.empty:
    try:
        if len(bm_prices_full) >= 200:
            m_bull = bool(bm_prices_full.iloc[-1] > bm_prices_full.rolling(200).mean().iloc[-1])
        elif len(bm_prices_full) >= 50:
            m_bull = bool(bm_prices_full.iloc[-1] > bm_prices_full.rolling(50).mean().iloc[-1])
        else:
            m_bull = True
    except:
        m_bull = False

st.markdown(f'<div class="status-box" style="background-color:{"#238636" if m_bull else "#da3633"};color:white;">MARKET STATUS: {"BULLISH 🟢" if m_bull else "BEARISH 🔴"} | REGIME: {"BULL ▲" if m_bull else "BEAR ▼"}</div>', unsafe_allow_html=True)

c_i1, c_i2, c_i3 = st.columns(3)
with c_i1:
    st.markdown(f'''<div class="intel-box" style="border-color:#238636;">
        <b>🧠 Marktphase: {m_ph}</b><br><small style="color:#8b949e;">Wyckoff / Weinstein Modell</small><br><br>
        <span style="font-size:0.92em;">{m_adv}</span>
    </div>''', unsafe_allow_html=True)
with c_i2:
    mood_color = "#3fb950" if s_mood in ["Bullish","Sehr Stark"] else "#f85149" if s_mood in ["Schwach","Vorsicht"] else "#e3b341"
    st.markdown(f'''<div class="intel-box" style="border-color:#f1e05a;">
        <b>📅 Saisonalität: {s_name}</b><br>
        <span style="color:{mood_color};font-weight:bold;">{s_mood}</span><br><br>
        <span style="font-size:0.92em;">{s_detail}</span>
    </div>''', unsafe_allow_html=True)
with c_i3:
    rsi_color = "#f85149" if rsi_val>=65 else "#3fb950" if rsi_val<=35 else "#e3b341"
    st.markdown(f'''<div class="intel-box" style="border-color:#388bfd;">
        <b>📊 Sentiment: {m_sent}</b><br>
        <span style="color:{rsi_color};font-weight:bold;font-size:1.1em;">RSI S&P 500: {rsi_val:.1f}</span><br><br>
        <span style="font-size:0.92em;">{sent_desc}</span>
    </div>''', unsafe_allow_html=True)

# ── 6. CHECKLIST ──────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown("## 📋 Market Conditions Checklist")
bm_tuple = (list(bm_prices_full.index.astype(str)), list(bm_prices_full.values))
with st.spinner("Checklist..."):
    checklist = get_market_checklist(bm_tuple)

checks  = list(checklist.values())
passed  = sum(1 for c in checks if c['pass'] is True)
total_c = len(checks)

if passed == total_c:
    banner_class, banner_icon = "check-banner-green","✅"
    banner_text = f"Alle {total_c}/{total_c} Bedingungen erfüllt — Volle Investitionsquote empfohlen"
elif passed >= 3:
    banner_class, banner_icon = "check-banner-yellow","⚠️"
    banner_text = f"{passed}/{total_c} Bedingungen erfüllt — Reduzierte Position (75%)"
elif passed >= 2:
    banner_class, banner_icon = "check-banner-yellow","⚠️"
    banner_text = f"{passed}/{total_c} Bedingungen erfüllt — Vorsicht, höheres Risiko (50%)"
else:
    banner_class, banner_icon = "check-banner-red","🚫"
    banner_text = f"Nur {passed}/{total_c} Bedingungen — Cash-Modus empfohlen"

st.markdown(f'<div class="{banner_class}">{banner_icon} {banner_text}</div>', unsafe_allow_html=True)

check_meta = {
    'regime':  ("📈","Regime Check","S&P 500 über SMA 200?"),
    'breadth': ("🌐","Breadth Check",">50% Aktien über SMA 50?"),
    'vix':     ("🌡️","VIX Check","VIX unter 25?"),
    'abs_mom': ("⚡","Absolute Momentum","12M-Rendite positiv?"),
}
cols = st.columns(4)
for i,(key,meta) in enumerate(check_meta.items()):
    c = checklist.get(key,{})
    icon,title,question = meta
    if c.get('pass') is True:
        si,bc,ans,ac = "✅","#238636","JA","#3fb950"
    elif c.get('pass') is False:
        si,bc,ans,ac = "❌","#da3633","NEIN","#f85149"
    else:
        si,bc,ans,ac = "⚠️","#b18c00","N/A","#e3b341"
    with cols[i]:
        st.markdown(f'''<div class="checklist-card" style="border-left:4px solid {bc};">
            <div style="font-size:1.6em;margin-bottom:4px;">{si} {icon}</div>
            <div class="checklist-title">{title}</div>
            <div class="checklist-subtitle">{question}</div>
            <div style="font-size:1.4em;font-weight:bold;color:{ac};margin-top:8px;">{ans}</div>
            <div class="checklist-subtitle" style="margin-top:4px;">{c.get("desc","")}</div>
        </div>''', unsafe_allow_html=True)

st.markdown("---")

# ── 7. TABS ───────────────────────────────────────────────────────────────────
t1,t2,t3,t4,t5 = st.tabs(["🎯 Action Plan","🔭 Scanner","📈 Charts","🧪 Backtest","📖 Market Intelligence"])

# ── TAB 1: ACTION PLAN ────────────────────────────────────────────────────────
with t1:
    res = []
    if not bm_prices_full.empty:
        bm_rsi_val = calc_rsi(bm_prices_full.dropna()).iloc[-1]
        res.append({"Ticker":"^GSPC","Name":"S&P 500 Index (Benchmark)","Sector":"Benchmark","RS Score":0.0,"RSI(14)":bm_rsi_val,"Action":"🟢 HOLD (BULLISH)" if m_bull else "🔴 SELL (BEARISH)"})
    for t in portfolio_list:
        if t in live_port_prices.columns:
            p = live_port_prices[t].dropna()
            rs_s = calc_rs_stable(p, bm_prices_full.reindex(p.index).ffill())
            ri_s = calc_rsi(p)
            if not rs_s.empty and not ri_s.empty:
                d = get_company_static_info(t)
                res.append({"Ticker":t,"Name":d["Name"],"Sector":d["Sector"],"RS Score":rs_s.iloc[-1],"RSI(14)":ri_s.iloc[-1],"Action":"🟢 HOLD" if rs_s.iloc[-1]>0 else "🔴 SELL"})
    if res:
        st.dataframe(pd.DataFrame(res).sort_values("RS Score",ascending=False).style.background_gradient(subset=['RS Score'],cmap='RdYlGn').format(subset=['RS Score','RSI(14)'],formatter="{:.2f}"),width='stretch',hide_index=True)

# ── TAB 2: SCANNER ────────────────────────────────────────────────────────────
with t2:
    if st.button("🚀 Run S&P 500 Scan"):
        with st.spinner("Scanning S&P 500 Leaders..."):
            prices, companies = get_db_data()
            if prices is not None:
                sp_data   = prices.ffill()
                opps      = []
                info_dict = companies.set_index('Symbol').to_dict('index')
                sp500_tk  = get_sp500_list()
                for t in sp_data.columns:
                    if t not in sp500_tk or t=="^GSPC" or t in portfolio_list: continue
                    p = sp_data[t].dropna()
                    if len(p)<60: continue
                    rs_s = calc_rs_stable(p, bm_prices_full.reindex(p.index).ffill())
                    if not rs_s.empty and rs_s.iloc[-1]>0.12:
                        d = info_dict.get(t,{"Security":t,"GICS Sector":"N/A"})
                        opps.append({"Ticker":t,"Name":d["Security"],"Sector":d["GICS Sector"],"RS Score":rs_s.iloc[-1]})
                if opps:
                    st.table(pd.DataFrame(opps).sort_values("RS Score",ascending=False).head(15))
                    st.code(", ".join(pd.DataFrame(opps)['Ticker'].tolist()), language="text")
                else:
                    st.info("Keine neuen Leader gefunden.")
            else:
                st.error("Datenbank nicht gefunden.")

# ── TAB 3: CHARTS ─────────────────────────────────────────────────────────────
with t3:
    sel = st.selectbox("Deep Dive Asset:", portfolio_list)
    if sel:
        if db_prices is not None and sel in db_prices.columns:
            df_c = db_prices[[sel]].dropna(); df_c.columns=['Close']
        else:
            df_c = yf.download(sel, period="1y", progress=False, auto_adjust=True)
        if isinstance(df_c.columns, pd.MultiIndex): df_c.columns = df_c.columns.get_level_values(0)
        if 'Open' not in df_c.columns:
            df_c = yf.download(sel, period="1y", progress=False, auto_adjust=True)
            if isinstance(df_c.columns, pd.MultiIndex): df_c.columns = df_c.columns.get_level_values(0)
        df_c['SMA50']  = df_c['Close'].rolling(50).mean()
        df_c['SMA200'] = df_c['Close'].rolling(200).mean()
        fig = make_subplots(rows=2,cols=1,shared_xaxes=True,row_heights=[0.7,0.3],vertical_spacing=0.05)
        fig.add_trace(go.Candlestick(x=df_c.index,open=df_c['Open'],high=df_c['High'],low=df_c['Low'],close=df_c['Close'],name="Price"),row=1,col=1)
        fig.add_trace(go.Scatter(x=df_c.index,y=df_c['SMA50'],line=dict(color='orange'),name="SMA 50"),row=1,col=1)
        fig.add_trace(go.Scatter(x=df_c.index,y=df_c['SMA200'],line=dict(color='red'),name="SMA 200"),row=1,col=1)
        rs_l = calc_rs_stable(df_c['Close'], bm_prices_full.reindex(df_c.index).ffill())
        if not rs_l.empty:
            fig.add_trace(go.Scatter(x=rs_l.index,y=rs_l,fill='tozeroy',line=dict(color='lime'),name="RS Score"),row=2,col=1)
        fig.update_layout(height=700,template="plotly_dark",xaxis_rangeslider_visible=False)
        st.plotly_chart(fig,width='stretch')

# ── TAB 4: BACKTEST ───────────────────────────────────────────────────────────
with t4:
    # --- Backtest Description ---
    with st.expander("📖 Wie funktioniert dieser Backtest? (Methodologie)", expanded=False):
        st.markdown(f'''<div class="bt-info-card">
        <b>🔬 RS-Momentum Strategie — Backtest Methodologie</b><br><br>
        <b>Prinzip:</b> Jeden Monat werden die {5} Aktien mit dem stärksten <i>Relativen Stärke (RS) Score</i> vs. dem S&P 500 ausgewählt und gleichgewichtet gekauft.<br><br>
        <b>RS Score:</b> Verhältnis der Aktie zum S&P 500, normiert über einen 50-Tage-Durchschnitt. Werte > 0 = Outperformer.<br><br>
        <b>Kapital-Exposure:</b><br>
        &nbsp;&nbsp;• <b>Bullenmarkt</b> (S&P 500 > SMA 200) → <b>100%</b> investiert<br>
        &nbsp;&nbsp;• <b>Bärenmarkt</b> (S&P 500 < SMA 200) → <b>20%</b> investiert, 80% Cash<br><br>
        <b>Stop Loss:</b> Jede Position wird automatisch verkauft, wenn sie {sl_input_val}% unter den Einstandskurs fällt.<br><br>
        <b>Transaktionskosten:</b> 0.12% pro Trade werden abgezogen (Spread + Provision).<br><br>
        <b>Rebalancing:</b> Jeden Monat (oder nach gewählter Halteperiode) wird das Portfolio neu ausgerichtet.
        </div>''', unsafe_allow_html=True)

    # --- Earnings Calendar ---
    st.markdown("### 📅 Earnings Kalender — Watchlist")
    with st.spinner("Lade Earnings-Daten..."):
        earn_df = get_earnings_calendar(portfolio_list)
    if not earn_df.empty:
        def beat_color(val):
            if 'Beat' in str(val): return 'color: #3fb950; font-weight: bold'
            if 'Miss' in str(val): return 'color: #f85149; font-weight: bold'
            return ''
        st.dataframe(earn_df.style.map(beat_color, subset=['Last Q Beat/Miss']), width='stretch', hide_index=True)

    st.markdown("---")
    # --- News Feed ---
    st.markdown("### 📰 Markt-Newsfeed")
    with st.spinner("Lade aktuelle Nachrichten..."):
        news = get_market_news_feed()
    if news:
        for n in news[:12]:
            st.markdown(f'''<div class="news-card">
                <a href="{n['link']}" target="_blank" style="color:#e6edf3;text-decoration:none;font-weight:bold;">{n['title']}</a>
                <div style="font-size:0.78em;color:#8b949e;margin-top:3px;">{n.get('published','')}</div>
            </div>''', unsafe_allow_html=True)
    else:
        st.info("Keine aktuellen Nachrichten geladen.")

    st.markdown("---")
    # --- Backtest Engine ---
    col_c1, col_c2 = st.columns(2)
    cap_in = col_c1.number_input("Backtest Capital (USD):", value=10000)
    n_st   = col_c2.slider("Positions:", 3, 10, 5)

    if st.button("🧪 Execute Advanced Backtest"):
        with st.spinner("Processing History..."):
            ticks_bt = portfolio_list if bt_univ_choice=="Watchlist" else get_sp500_list()
            s_date   = f"{bt_s_year}-01-01"
            e_date   = f"{bt_e_year}-12-31"
            s_p_date = datetime.strptime(s_date,"%Y-%m-%d") - timedelta(days=450)
            s_p      = s_p_date.strftime("%Y-%m-%d")

            if db_prices is not None and not db_prices.empty and db_prices.index[0]<=s_p_date and db_prices.index[-1]>=datetime.strptime(s_date,"%Y-%m-%d"):
                st.info("Using Database for Backtest...")
                bt_data_full = db_prices.loc[s_p:e_date]
            else:
                st.info("Downloading history from yfinance...")
                bt_data_full = yf.download(ticks_bt+["^GSPC"],start=s_p,end=e_date,progress=False,threads=True,auto_adjust=True)['Close']

            if isinstance(bt_data_full.columns, pd.MultiIndex):
                bt_data_full.columns = bt_data_full.columns.get_level_values(0)

            bt_d   = bt_data_full.ffill()
            bm_f   = bt_d["^GSPC"]
            common = bt_d.index.intersection(bm_f.index)
            bt_d, bm_f = bt_d.loc[common], bm_f.loc[common]

            rs_dict = {t: calc_rs_stable(bt_d[t], bm_f) for t in ticks_bt if t in bt_d.columns and t!="^GSPC"}
            rs_h    = pd.concat(rs_dict, axis=1)

            t_d = bt_d.loc[s_date:].groupby(pd.Grouper(freq=f'{hold_mo_val}ME')).apply(lambda x: x.index[-1] if not x.empty else None).dropna()
            c, c_h, t_l, f_dt = cap_in, [], [], None

            for i in range(len(t_d)-1):
                cur, nxt = t_d.iloc[i], t_d.iloc[i+1]
                is_bul   = bm_f.loc[cur] > bm_f.rolling(200).mean().loc[cur]
                exp      = 1.0 if is_bul else 0.2
                rank     = rs_h.loc[cur].dropna().sort_values(ascending=False).head(n_st)
                if len(rank)<n_st: continue
                if f_dt is None: f_dt=cur
                p_r, det = [], []
                for tk in rank.index.tolist():
                    bp, dp = bt_d.loc[cur,tk], bt_d.loc[cur:nxt,tk]
                    if dp.min() <= bp*(1-sl_input_val/100): ex_p,stt = bp*(1-sl_input_val/100),"🚨SL"
                    else: ex_p,stt = dp.iloc[-1],"OK"
                    p_r.append((c*exp/n_st)*0.9988*(ex_p/bp))
                    g = (ex_p/bp-1)*100
                    det.append(f"{tk}({'🟢' if g>0 else '🔴'}{g:+.1f}%, In:{bp:.1f}/Out:{ex_p:.1f},{stt})")
                c_pv = c; c = sum(p_r)+(c*(1-exp))
                s_pf = (c/c_pv-1)*100; b_pf=(bm_f.loc[nxt]/bm_f.loc[cur]-1)*100
                c_h.append({"Date":nxt,"Strategy":c,"Market":(bm_f.loc[nxt]/bm_f.loc[f_dt])*cap_in,"StratPerf":s_pf})
                t_l.append({"Date":cur.date(),"Regime":"BULL" if is_bul else "BEAR","Trades":" | ".join(det),"Strat%":s_pf,"S&P500%":b_pf,"Alpha%":s_pf-b_pf,"Value":c})

            if c_h:
                res = pd.DataFrame(c_h).set_index("Date")
                def m_dd(s): return ((s-s.cummax())/s.cummax()).min()*100
                perf = res['StratPerf']
                streak,max_streak=0,0
                for p in perf:
                    streak = streak+1 if p<0 else 0
                    max_streak = max(max_streak,streak)

                strat_total = (c/cap_in-1)*100
                index_total = (res['Market'].iloc[-1]/cap_in-1)*100
                dd_s,dd_i   = m_dd(res['Strategy']),m_dd(res['Market'])
                ann_f       = np.sqrt(12/hold_mo_val)
                sharpe      = (perf.mean()/100/(perf.std()/100))*ann_f if perf.std()>0 else 0
                vol         = (perf.std()/100)*ann_f*100

                m1,m2,m3,m4,m5 = st.columns(5)
                m1.metric("Final Capital",f"{c:,.0f} USD",f"{strat_total:+.1f}% Total")
                m2.metric("Alpha vs S&P 500",f"{strat_total-index_total:+.1f}%",f"Index: {index_total:+.1f}%")
                m3.metric("Max DD Strat",f"{dd_s:.1f}%",f"Index: {dd_i:.1f}%",delta_color="inverse")
                m4.metric("Sharpe Ratio",f"{sharpe:.2f}","Annualized")
                m5.metric("Volatility",f"{vol:.1f}%","Annualized")
                st.write(f"**Längste Pechsträhne:** {max_streak} Monate in Folge mit Verlust.")

                fig_p = go.Figure()
                fig_p.add_trace(go.Scatter(x=res.index,y=res['Strategy'],name="Strategy",line=dict(color='lime',width=3)))
                fig_p.add_trace(go.Scatter(x=res.index,y=res['Market'],name="S&P 500",line=dict(color='gray',dash='dash')))
                fig_p.update_layout(template="plotly_dark",height=400)
                st.plotly_chart(fig_p,width='stretch')

                log_df = pd.DataFrame(t_l).sort_values("Date",ascending=False)
                st.dataframe(
                    log_df.style
                    .map(lambda x:'background-color:#238636;color:white' if str(x)=="BULL" else 'background-color:#da3633;color:white' if str(x)=="BEAR" else '',subset=['Regime'])
                    .map(lambda x:'color:#3fb950;font-weight:bold' if isinstance(x,float) and x>0 else 'color:#f85149' if isinstance(x,float) and x<0 else '',subset=['Alpha%'])
                    .format(subset=['Strat%','S&P500%','Alpha%'],formatter="{:+.2f}%")
                    .format(subset=['Value'],formatter="{:,.0f}"),
                    width='stretch',hide_index=True
                )

# ── TAB 5: MARKET INTELLIGENCE ────────────────────────────────────────────────
with t5:
    st.header("📈 Market Intelligence Hub")

    # --- 4 Marktphasen ---
    st.subheader("🔄 Die 4 Marktphasen nach Wyckoff / Weinstein")
    phases = [
        ("#388bfd","📈 Phase 1: Akkumulation","Bodenbildung nach einem Downtrend. Institutionelle Käufer akkumulieren im Verborgenen. Volumen beginnt zu steigen, Preis konsolidiert seitwärts. <b>Handelsstrategie:</b> Selektiv erste Positionen aufbauen. RS-Ausbrüche als Frühindikator beobachten. Noch kein Vollgas."),
        ("#3fb950","🚀 Phase 2: Markup (Aufwärtstrend)","Preis bricht über Widerstand. Öffentlichkeit wird bullish. SMA 50 > SMA 200 (Golden Cross). Momentum-Strategien liefern beste Renditen. <b>Handelsstrategie:</b> Volle Investitionsquote in RS-Leader. Stops unter SMA 50 setzen. Trend ist dein Freund."),
        ("#e3b341","⚠️ Phase 3: Distribution","Markt verliert Schwung. Volumen sinkt an Up-Days. Institutionelle Anleger verteilen ihre Positionen an Retail-Investoren. <b>Handelsstrategie:</b> Neue Positionen vermeiden. Bestehende Positionen mit engen Trailing-Stops sichern. Gewinner realisieren."),
        ("#f85149","🔴 Phase 4: Markdown (Abwärtstrend)","Bestätigter Bärenmarkt. SMA 50 unter SMA 200 (Death Cross). Preis < SMA 200. Institutionelle Anleger sind raus – Retail fängt fallende Messer. <b>Handelsstrategie:</b> 80-100% Cash. Keine neuen Long-Positionen. Kapitalschutz hat absolute Priorität. Short-ETFs als Alternative."),
    ]
    ph_cols = st.columns(4)
    for i,(color,title,desc) in enumerate(phases):
        with ph_cols[i]:
            st.markdown(f'''<div class="phase-card" style="border-top:4px solid {color};">
                <div style="color:{color};font-weight:bold;margin-bottom:8px;">{title}</div>
                <div style="font-size:0.88em;line-height:1.6;">{desc}</div>
            </div>''', unsafe_allow_html=True)

    st.markdown("---")

    col1, col2 = st.columns([1.2,1])
    with col1:
        st.subheader("📅 Saisonaler Jahreskalender")
        monthly = [
            ("Jan","Bullish","#3fb950"),("Feb","Volatil","#e3b341"),("Mär","Bullish","#3fb950"),
            ("Apr","Sehr Stark","#3fb950"),("Mai","Vorsicht","#f85149"),("Jun","Neutral","#8b949e"),
            ("Jul","Bullish","#3fb950"),("Aug","Schwach","#f85149"),("Sep","Schwach","#f85149"),
            ("Okt","Volatil","#e3b341"),("Nov","Sehr Stark","#3fb950"),("Dez","Bullish","#3fb950"),
        ]
        curr_month = datetime.now().month
        cal_html = '<div style="display:flex;flex-wrap:wrap;gap:8px;margin-top:10px;">'
        for idx,(mon,mood,color) in enumerate(monthly):
            border = "3px solid white" if idx+1==curr_month else "1px solid #30363d"
            cal_html += f'<div style="background:#161b22;border:{border};border-radius:8px;padding:10px 12px;text-align:center;min-width:70px;"><b>{mon}</b><br><span style="color:{color};font-size:0.82em;">{mood}</span></div>'
        cal_html += '</div>'
        st.markdown(cal_html, unsafe_allow_html=True)

        st.markdown(f"<br><div class='outlook-card'><b>Aktuell: {s_name}</b> — <span style='color:#e3b341;'>{s_mood}</span><br><br>{s_detail}<br><br><b>Roadmap:</b> Beste Saisonalität Nov–Apr. Sommer (Mai–Okt) defensiver.</div>", unsafe_allow_html=True)

    with col2:
        st.subheader("🗓️ Wirtschaftliche Ereignisse (nächste 45 Tage)")
        upcoming = get_upcoming_events(45)
        if upcoming:
            for e in upcoming:
                days = e['days_until']
                day_label = "Heute!" if days==0 else f"in {days} Tagen"
                urgent_color = "#f85149" if days<=3 else "#e3b341" if days<=7 else "#8b949e"
                st.markdown(f'''<div class="calendar-event">
                    {e["impact"]} <b>{e["date"]}</b>
                    <span style="color:{urgent_color};font-size:0.82em;margin-left:8px;">{day_label}</span><br>
                    <span style="font-size:0.9em;">{e["event"]}</span>
                </div>''', unsafe_allow_html=True)
        else:
            st.info("Keine Events in den nächsten 45 Tagen.")

    st.markdown("---")
    st.markdown(f'<div class="disclaimer">⚠️ LEGAL NOTICE: Not financial advice. Investing involves risk of loss. © {datetime.now().year} Manuel Kössler.</div>', unsafe_allow_html=True)
