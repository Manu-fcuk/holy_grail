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
    
    # Add Revolut extra list so we cache all 1,000+ EU/Intl/Bond/Commodity tickers in the DB too!
    extra_revolut = [
        "NVO", "ASML", "NVS", "AZN", "SHEL", "TTE", "SAP", "SNY", "SIEGY", "HDB", "TSM", 
        "BABA", "NIO", "SONY", "SPOT", "SHOP", "PDD", "JD", "BIDU", "MNDY", "ARM",
        "TLT", "IEF", "SHY", "LQD", "HYG", "BND", "AGG", "EMB", "MBB",
        "GLD", "IAU", "SLV", "USO", "UNG", "PDBC", "DBA", "COPX", "URA", "PPLT", "PALL",
        'AA', 'AAL', 'AAP', 'ABEV', 'AEO', 'AG', 'AGNC', 'AI', 'AL', 'ALLT', 'ALLY', 'ALXN', 'AMC', 'AMH', 'AMRX', 'AMTD', 'ANF', 'ANGI', 'ANSS', 'ANTM', 'APPN', 'APPS', 'AR', 'ARCC', 'ARCT', 'ARI', 'ARMK', 'ARNC', 'ARR', 'ASAN', 'ASML', 'ATHM', 'ATR', 'ATUS', 'ATVI', 'AU', 'AUY', 'AVLR', 'AXL', 'AXTA', 'AYX', 'AZN', 'BABA', 'BAH', 'BAM', 'BAP', 'BB', 'BBAR', 'BBD', 'BDC', 'BEP', 'BEPC', 'BF.B', 'BHC', 'BHP', 'BIDU', 'BILI', 'BIO', 'BIP', 'BIPC', 'BITA', 'BJ', 'BLL', 'BMA', 'BMRN', 'BNTX', 'BOX', 'BP', 'BRFS', 'BRK.B', 'BRX', 'BSBR', 'BSMX', 'BTG', 'BUD', 'BVN', 'BWA', 'BYND', 'BZUN', 'CABO', 'CAJ', 'CARS', 'CC', 'CDE', 'CERN', 'CG', 'CGNX', 'CHGG', 'CHKP', 'CHL', 'CHS', 'CHWY', 'CIG', 'CIM', 'CLDR', 'CLF', 'CLNY', 'CLR', 'CLVS', 'CMA', 'CNDT', 'CNX', 'COG', 'COLD', 'COMM', 'COTY', 'CROX', 'CRSP', 'CTXS', 'CVE', 'CWEN', 'CX', 'CXO', 'CY', 'CYH', 'CZR', 'DAN', 'DBX', 'DFS', 'DHC', 'DIN', 'DISCA', 'DISCK', 'DISH', 'DKNG', 'DNKN', 'DOCU', 'DRE', 'DXC', 'EB', 'EDU', 'EGO', 'ELAN', 'ENIA', 'ENLC', 'ENPH', 'EPD', 'EQH', 'EQNR', 'ERJ', 'ESI', 'ET', 'ETFC', 'ETRN', 'ETSY', 'EVR', 'EXAS', 'EXEL', 'FB', 'FEYE', 'FHN', 'FIT', 'FL', 'FLEX', 'FLR', 'FLT', 'FOLD', 'FREQ', 'FROG', 'FSK', 'FSLY', 'FTI', 'FVE', 'FVRR', 'FWONK', 'GDS', 'GEO', 'GES', 'GFI', 'GGAL', 'GGB', 'GLUU', 'GME', 'GMED', 'GNL', 'GNTX', 'GNW', 'GO', 'GOL', 'GOLD', 'GPK', 'GPRO', 'GPS', 'GRPN', 'GRUB', 'GSK', 'GT', 'GWPH', 'H', 'HBI', 'HCM', 'HDB', 'HEI', 'HES', 'HFC', 'HGV', 'HIMX', 'HL', 'HLF', 'HMC', 'HMY', 'HOG', 'HOME', 'HRB', 'HTHT', 'HUBS', 'HUN', 'HUYA', 'IAG', 'IBN', 'ICPT', 'IGMS', 'IGT', 'IIPR', 'ILMN', 'IMGN', 'INFN', 'INFY', 'INO', 'IPG', 'IQ', 'IRBT', 'ISBC', 'ITUB', 'IVR', 'JBLU', 'JD', 'JEF', 'JKS', 'JMIA', 'JNPR', 'JWN', 'K', 'KAR', 'KGC', 'KNX', 'KSS', 'KT', 'KTOS', 'LB', 'LESL', 'LEVI', 'LI', 'LKQ', 'LMND', 'LNG', 'LOGI', 'LOMA', 'LP', 'LPL', 'LSCC', 'LTC', 'LTHM', 'LUMN', 'LVGO', 'LX', 'LXRX', 'LYFT', 'M', 'MAT', 'MAXN', 'MBT', 'MCFE', 'MDB', 'MDRX', 'MELI', 'MFA', 'MFG', 'MGI', 'MIK', 'MKL', 'MLCO', 'MMC', 'MOMO', 'MORN', 'MPLX', 'MPW', 'MRO', 'MRVL', 'MSGS', 'MSP', 'MTDR', 'MTG', 'MUFG', 'MUR', 'MUX', 'MXIM', 'MYL', 'NAVI', 'NBEV', 'NBIX', 'NET', 'NICE', 'NIO', 'NKLA', 'NKTR', 'NLOK', 'NLY', 'NMR', 'NOAH', 'NOV', 'NPTN', 'NRZ', 'NTCO', 'NTES', 'NTNX', 'NUVA', 'NVAX', 'NVCR', 'NVTA', 'NWL', 'NYCB', 'NYMT', 'NYT', 'OASPQ', 'ODP', 'OKTA', 'OLN', 'OPK', 'OSTK', 'OVV', 'PAA', 'PAAS', 'PAM', 'PBCT', 'PBF', 'PBH', 'PBI', 'PBR', 'PD', 'PDCE', 'PDD', 'PENN', 'PFPT', 'PINS', 'PLAN', 'PLNT', 'PLUG', 'PRI', 'PS', 'PSTG', 'PTEN', 'PTON', 'PXD', 'QD', 'QLYS', 'QRTEA', 'QSR', 'QTWO', 'RACE', 'RAD', 'RDFN', 'REAL', 'REGI', 'RES', 'RH', 'RKT', 'RLGY', 'RNG', 'ROKU', 'ROOT', 'RRC', 'RUN', 'RXT', 'RY', 'SAVE', 'SBH', 'SBS', 'SBSW', 'SCCO', 'SE', 'SEB', 'SEDG', 'SFIX', 'SFM', 'SGMO', 'SHAK', 'SHOP', 'SID', 'SIRI', 'SKT', 'SKX', 'SLB', 'SLCA', 'SLM', 'SM', 'SMAR', 'SMFG', 'SMG', 'SNAP', 'SNE', 'SNOW', 'SOGO', 'SPCE', 'SPLK', 'SPOT', 'SPWR', 'SQ', 'SQM', 'SSNC', 'SSSS', 'STAY', 'STLA', 'STNE', 'SU', 'SUMO', 'SUPV', 'SWN', 'TAK', 'TAL', 'TCOM', 'TD', 'TDOC', 'TEAM', 'TECK', 'TEVA', 'TFX', 'TGI', 'TIF', 'TIGR', 'TIMB', 'TLRDQ', 'TM', 'TME', 'TPX', 'TRIP', 'TSM', 'TTM', 'TV', 'TW', 'TWLO', 'TWO', 'TWOU', 'TWTR', 'TXMD', 'U', 'UA', 'UAA', 'UCTT', 'UGP', 'UMC', 'UNIT', 'UNM', 'URBN', 'UXIN', 'VALE', 'VEEV', 'VER', 'VFC', 'VG', 'VGR', 'VIACA', 'VIPS', 'VIR', 'VIV', 'VMW', 'VRM', 'W', 'WB', 'WBA', 'WEN', 'WEX', 'WING', 'WIT', 'WIX', 'WKHS', 'WORK', 'WPX', 'WRK', 'WTM', 'WU', 'WUBA', 'WWE', 'X', 'XEC', 'XGN', 'XLNX', 'XPEV', 'XRX', 'YETI', 'YPF', 'YUMC', 'YY', 'Z', 'ZEN', 'ZION', 'ZM', 'ZNGA', 'ZNH', 'ZS', 'ZTO',
        # Crypto
        "BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "ADA-USD", "DOGE-USD",
        "DOT-USD", "MATIC-USD", "SHIB-USD", "LTC-USD", "AVAX-USD", "LINK-USD", "UNI-USD"
    ]
    tickers.extend([t for t in extra_revolut if t not in tickers])
    
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

        # Verwende hier maximal 2 Threads und ein Sleep, da Yahoo Finance sonst die IP blockt ("Rate Limit Error")
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
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
