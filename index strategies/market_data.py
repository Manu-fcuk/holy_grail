import yfinance as yf
import pandas as pd
import ta
from textblob import TextBlob
from datetime import datetime, timedelta

def get_stock_data(ticker, interval, period="1d"):
    """
    Fetch stock data from yfinance.
    For intraday 1m data, period is limited to 7d.
    """
    try:
        data = yf.download(ticker, period=period, interval=interval, progress=False)
        if data.empty:
            return None
        
        # Ensure we have a clean index and columns
        data.columns = [col[0] if isinstance(col, tuple) else col for col in data.columns]
        
        return data
    except Exception as e:
        print(f"Error fetching data: {e}")
        return None

def calculate_signals(df):
    """
    Calculate indicators and Buy/Sell signals for multiple strategies.
    Strategies:
    1. EMA Crossover (Trend)
    2. RSI + Bollinger Bands (Mean Reversion)
    3. VWAP Pullback (Trend Following - Simplistic approximation)
    """
    if df is None or df.empty:
        return df

    # Initialize columns to avoid KeyErrors if data is insufficient for indicators
    # and we return early.
    expected_cols = ['Signal_EMA', 'Signal_RSI_BB', 'Signal_VWAP', 'Signal_ORB', 
                     'EMA_9', 'EMA_21', 'RSI', 
                     'BB_High', 'BB_Low', 'BB_Mid', 'VWAP', 'ORB_High', 'ORB_Low']
    for col in expected_cols:
        if col not in df.columns:
            df[col] = 0.0

    # Need enough data for the longest window (BB=20, EMA=21)
    if len(df) < 21:
        return df

    # --- Indicators ---
    # EMA
    df['EMA_9'] = ta.trend.EMAIndicator(df['Close'], window=9).ema_indicator()
    df['EMA_21'] = ta.trend.EMAIndicator(df['Close'], window=21).ema_indicator()
    
    # RSI
    df['RSI'] = ta.momentum.RSIIndicator(df['Close'], window=14).rsi()
    
    # Bollinger Bands
    bb_indicator = ta.volatility.BollingerBands(close=df['Close'], window=20, window_dev=2)
    df['BB_High'] = bb_indicator.bollinger_hband()
    df['BB_Low'] = bb_indicator.bollinger_lband()
    df['BB_Mid'] = bb_indicator.bollinger_mavg()
    
    # VWAP (Volume Weighted Average Price)
    # Note: ta library VWAP might return NaN if volume is 0 or missing
    try:
        vwap = ta.volume.VolumeWeightedAveragePrice(
            high=df['High'], low=df['Low'], close=df["Close"], volume=df['Volume'], window=14
        )
        df['VWAP'] = vwap.volume_weighted_average_price()
    except Exception:
        df['VWAP'] = df['BB_Mid'] # Fallback if Volume issue

    # --- Strategy 1: EMA Crossover ---
    df.loc[df['EMA_9'] > df['EMA_21'], 'Signal_EMA'] = 1
    df.loc[df['EMA_9'] < df['EMA_21'], 'Signal_EMA'] = -1

    # --- Strategy 2: RSI + Bollinger Bands (Mean Reversion) ---
    # Buy: Price touches Lower Band AND RSI < 30
    # Sell: Price touches Upper Band AND RSI > 70
    
    df.loc[(df['Close'] <= df['BB_Low']) & (df['RSI'] < 30), 'Signal_RSI_BB'] = 1
    df.loc[(df['Close'] >= df['BB_High']) & (df['RSI'] > 70), 'Signal_RSI_BB'] = -1
    
    # --- Strategy 3: VWAP Trend ---
    # Buy: Close crosses Above VWAP
    # Sell: Close crosses Below VWAP
    df.loc[df['Close'] > df['VWAP'], 'Signal_VWAP'] = 1
    df.loc[df['Close'] < df['VWAP'], 'Signal_VWAP'] = -1

    # --- Strategy 4: Opening Range Breakout (ORB 15m) ---
    # 1. Identify today's data (assuming index is datetime)
    if len(df) > 0:
        # Get the date of the last bar to ensure we are looking at the 'current' trading session in the data
        last_date = df.index[-1].date()
        today_data = df[df.index.date == last_date]
        
        if len(today_data) > 0:
            # 2. Get Start Time of session (first bar)
            # Market typically opens 9:30 ET. We'll take the first 15 minutes from the first timestamp found for today
            # assuming the data request started early enough or covers the open.
            start_time = today_data.index[0]
            end_time_orb = start_time + timedelta(minutes=15)
            
            # 3. Calculate Range (High/Low)
            orb_data = today_data[today_data.index < end_time_orb]
            
            # We need at least some bars in the first 15m
            if not orb_data.empty:
                orb_high = orb_data['High'].max()
                orb_low = orb_data['Low'].min()
                
                # Assign to columns for visualization (fill forward for the whole day)
                # Initialize with NaN so we don't plot lines before they exist
                df['ORB_High'] = None 
                df['ORB_Low'] = None
                
                # Set values for today
                mask_today = df.index.date == last_date
                df.loc[mask_today, 'ORB_High'] = orb_high
                df.loc[mask_today, 'ORB_Low'] = orb_low
                
                # 4. Generate Signals (Only valid AFTER the ORB period)
                # Buy: Close > ORB_High
                # Sell: Close < ORB_Low
                df['Signal_ORB'] = 0
                
                # Logic: We are in a "Buy" zone if price is above ORB High AND we are past the ORB period
                # Logic: We are in a "Sell" zone if price is below ORB Low AND we are past the ORB period
                
                is_after_orb = (df.index > end_time_orb) & mask_today
                
                df.loc[is_after_orb & (df['Close'] > orb_high), 'Signal_ORB'] = 1
                df.loc[is_after_orb & (df['Close'] < orb_low), 'Signal_ORB'] = -1
    
    return df

import feedparser

def _parse_sentiment(text):
    score = TextBlob(text).sentiment.polarity
    label = "Positive" if score > 0.1 else ("Negative" if score < -0.1 else "Neutral")
    return score, label

def get_news_sentiment(ticker):
    """
    Fetch news with 3-level fallback:
    1. yfinance native (handles both old & new API structure)
    2. Yahoo Finance RSS feed for ticker
    3. General Yahoo Finance market news
    """
    processed_news = []

    # --- 1. yfinance Native News ---
    try:
        ticker_obj = yf.Ticker(ticker)
        news_list = ticker_obj.news or []
        for item in news_list:
            # New yfinance structure wraps data inside 'content'
            content = item.get("content", item)  # fallback to item itself for old structure
            
            title = (content.get("title") or item.get("title") or "").strip()
            if not title:
                continue

            # Publisher: new structure has nested 'provider' dict
            provider = content.get("provider", {})
            publisher = provider.get("displayName") or item.get("publisher") or "Unknown"

            # Link: new structure uses canonicalUrl
            canonical = content.get("canonicalUrl", {})
            link = canonical.get("url") or item.get("link") or "#"

            # Published time: new format uses ISO string 'pubDate', old uses Unix timestamp
            pub_raw = content.get("pubDate") or ""
            if pub_raw:
                try:
                    # e.g. "2024-02-24T13:00:00Z"
                    published = datetime.strptime(pub_raw[:19], "%Y-%m-%dT%H:%M:%S").strftime("%Y-%m-%d %H:%M")
                except Exception:
                    published = pub_raw
            else:
                ts = item.get("providerPublishTime", 0)
                published = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M") if ts else "N/A"

            summary = content.get("summary") or item.get("summary") or ""
            score, label = _parse_sentiment(f"{title}. {summary}" if summary else title)

            processed_news.append({
                "title": title,
                "link": link,
                "publisher": publisher,
                "sentiment": label,
                "score": score,
                "published": published,
            })
    except Exception as e:
        print(f"yfinance news error: {e}")

    # Filter out any items that still have garbage timestamps or unknown publisher
    good_news = [n for n in processed_news if n["published"] not in ("1970-01-01 01:00", "N/A") and n["publisher"] != "Unknown"]
    if good_news:
        return pd.DataFrame(good_news)

    # --- 2. Yahoo Finance RSS for Ticker ---
    try:
        rss_url = f"https://finance.yahoo.com/rss/headline?s={ticker}"
        feed = feedparser.parse(rss_url)
        for entry in feed.entries:
            title = entry.get("title", "").strip()
            if not title:
                continue
            summary = entry.get("summary", "")
            score, label = _parse_sentiment(f"{title}. {summary}" if summary else title)
            processed_news.append({
                "title": title,
                "link": entry.get("link", "#"),
                "publisher": "Yahoo Finance",
                "sentiment": label,
                "score": score,
                "published": entry.get("published", "N/A"),
            })
    except Exception as e:
        print(f"RSS news error: {e}")

    if processed_news:
        return pd.DataFrame(processed_news)

    # --- 3. General Market News Fallback ---
    try:
        feed = feedparser.parse("https://feeds.finance.yahoo.com/rss/2.0/headline?s=^GSPC&region=US&lang=en-US")
        if not feed.entries:
            feed = feedparser.parse("https://finance.yahoo.com/news/rssindex")
        for entry in feed.entries[:12]:
            title = entry.get("title", "").strip()
            if not title:
                continue
            score, label = _parse_sentiment(title)
            processed_news.append({
                "title": f"[Market] {title}",
                "link": entry.get("link", "#"),
                "publisher": "Yahoo News",
                "sentiment": label,
                "score": score,
                "published": entry.get("published", "N/A"),
            })
    except Exception as e:
        print(f"General news error: {e}")

    return pd.DataFrame(processed_news)
