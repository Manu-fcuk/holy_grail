import yfinance as yf
import pandas as pd
import sqlite3
import requests
from datetime import datetime
import os
import io

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "market_data.db")

def get_sp500_list():
    try:
        url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
        headers = {'User-Agent': 'Mozilla/5.0'}
        html_text = requests.get(url, headers=headers).text
        df = pd.read_html(io.StringIO(html_text))[0]
        df['Symbol'] = df['Symbol'].str.replace('.', '-')
        return df[['Symbol', 'Security', 'GICS Sector']]
    except Exception as e:
        print(f"Error fetching S&P 500 list: {e}")
        return pd.DataFrame()

def update_database():
    print("Starting Database Update...")
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    
    # 1. Update Company Info Table
    sp_df = get_sp500_list()
    if not sp_df.empty:
        sp_df.to_sql('companies', conn, if_exists='replace', index=False)
        print(f"Updated metadata for {len(sp_df)} companies.")

    # 2. Download Price Data
    tickers = sp_df['Symbol'].tolist()
    # Adding benchmark index
    tickers.append("^GSPC")
    
    print(f"Downloading data for {len(tickers)} tickers...")
    # Downloading 11 years to ensure 10y backtest + buffer for moving averages (200 SMA)
    data = yf.download(tickers, period="11y", progress=True, threads=True, auto_adjust=True)['Close']
    
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)

    # 3. Store in Database
    data.to_sql('prices', conn, if_exists='replace', index=True)
    
    # 4. Update Earnings Table (multithreaded to speed up)
    try:
        print("Downloading earnings data (this takes ~1-2 min)...")
        import concurrent.futures
        
        # Also grab some common requested ones from the watchlist which might not be in the ^GSPC (e.g., PLTR, ASML, TOST, SQ, CRWD...)
        extra_tickers = ["GOOG", "AAPL", "AMZN", "WMT", "T", "META", "NVDA", "TSLA", "MSFT", "LLY", "GE", "PYPL", "SNAP", "ASML", "PLTR"]
        all_e_tickers = list(set(tickers + extra_tickers))
        if "^GSPC" in all_e_tickers: all_e_tickers.remove("^GSPC")

        def fetch_earn(t):
            try:
                tk = yf.Ticker(t)
                try: inf = tk.info or {}
                except: inf = {}
                earn_date = "N/A"
                try:
                    cal = tk.calendar
                    if isinstance(cal, dict):
                        ed = cal.get('Earnings Date')
                        if ed: earn_date = str(ed[0])[:10] if isinstance(ed, (list, tuple)) else str(ed)[:10]
                    if earn_date == "N/A":
                        ed_df = tk.earnings_dates
                        if ed_df is not None and not ed_df.empty:
                            fut = ed_df[ed_df.index >= pd.Timestamp.now(tz='UTC')]
                            if not fut.empty: earn_date = str(fut.index[0])[:10]
                except: pass
                eps_est = inf.get('epsForwardQuarter') or inf.get('forwardEps')
                rev_est = inf.get('revenueEstimate') or inf.get('totalRevenue')
                beat_str = "N/A"
                try:
                    eh = tk.earnings_history
                    if eh is not None and not eh.empty:
                        eh_clean = eh.dropna(subset=['epsActual', 'epsEstimate']).sort_index(ascending=False)
                        if not eh_clean.empty:
                            last_q = eh_clean.iloc[0]
                            act, exp = last_q['epsActual'], last_q['epsEstimate']
                            if exp != 0:
                                surp = (act - exp) / abs(exp) * 100
                                beat_str = f"Beat +{surp:.1f}%" if act >= exp else f"Miss {surp:.1f}%"
                except: pass
                if beat_str == "N/A":
                    try:
                        ed_df = tk.earnings_dates
                        if ed_df is not None and not ed_df.empty and 'Reported EPS' in ed_df.columns:
                            past = ed_df[ed_df['Reported EPS'].notna()].sort_index(ascending=False)
                            if not past.empty:
                                act, est = past.iloc[0]['Reported EPS'], past.iloc[0]['EPS Estimate']
                                if pd.notna(est) and est != 0:
                                    beat_str = f"Beat +{(act-est)/abs(est)*100:.1f}%" if act >= est else f"Miss {(act-est)/abs(est)*100:.1f}%"
                    except: pass
                
                return {
                    "Ticker": t,
                    "Name": inf.get('shortName', t),
                    "Earnings Date": earn_date,
                    "EPS Est.": f"${eps_est:.2f}" if pd.notna(eps_est) else "N/A",
                    "Rev Est.": f"${rev_est/1e9:.1f}B" if pd.notna(rev_est) else "N/A",
                    "Last Q Beat/Miss": beat_str,
                }
            except:
                return {"Ticker":t,"Name":t,"Earnings Date":"N/A","EPS Est.":"N/A","Rev Est.":"N/A","Last Q Beat/Miss":"N/A"}

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            e_rows = list(executor.map(fetch_earn, all_e_tickers))
            
        e_df = pd.DataFrame(e_rows)
        e_df.to_sql('earnings', conn, if_exists='replace', index=False)
        print(f"Updated earnings data for {len(e_df)} companies.")
    except Exception as e:
        print(f"Earnings update failed: {e}")
    
    conn.close()
    print("Update complete. Database saved to:", DB_PATH)

if __name__ == "__main__":
    update_database()
