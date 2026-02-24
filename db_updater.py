import yfinance as yf
import pandas as pd
import sqlite3
import requests
from datetime import datetime
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "market_data.db")

def get_sp500_list():
    try:
        url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
        headers = {'User-Agent': 'Mozilla/5.0'}
        df = pd.read_html(requests.get(url, headers=headers).text)[0]
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
    # We store it in a long format for easier SQL querying or just as a large table
    # For simplicity and speed in the scanner, a wide table (Date as index, Tickers as columns) works well for SQLite
    data.to_sql('prices', conn, if_exists='replace', index=True)
    
    conn.close()
    print("Update complete. Database saved to:", DB_PATH)

if __name__ == "__main__":
    update_database()
