import yfinance as yf
import pandas as pd
import requests
import time
from datetime import datetime, time as dt_time
import pytz
import os

# --- Configuration ---
SYMBOL = "^NDX"  # Nasdaq 100 Index
INTERVAL = "1m" # 1 minute timeframe for signals
# Telegram Credentials
TELEGRAM_TOKEN = "8779026924:AAFpdJUJsJwlbPBui25kjM00XJ6VevmUj-s"
TELEGRAM_CHAT_ID = "5573886447"

# EMA Periods
EMA_FAST = 9
EMA_SLOW = 21

# Timezone
TZ_NYC = pytz.timezone("America/New_York")

def send_telegram(message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Error sending Telegram: {e}")

def get_signal():
    try:
        # Fetch enough data for EMAs (5d ensures we have enough data at market open)
        df = yf.download(SYMBOL, period="5d", interval=INTERVAL, progress=False)
        if df.empty or len(df) < EMA_SLOW:
            return None, None

        # Clean columns if needed (yfinance MultiIndex fix)
        df.columns = [col[0] if isinstance(col, tuple) else col for col in df.columns]

        # Calculate EMAs
        df['EMA_Fast'] = df['Close'].ewm(span=EMA_FAST, adjust=False).mean()
        df['EMA_Slow'] = df['Close'].ewm(span=EMA_SLOW, adjust=False).mean()

        # Get latest and previous states to detect crossover
        current_fast = df['EMA_Fast'].iloc[-1]
        current_slow = df['EMA_Slow'].iloc[-1]
        prev_fast = df['EMA_Fast'].iloc[-2]
        prev_slow = df['EMA_Slow'].iloc[-2]
        price = float(df['Close'].iloc[-1])

        # Buy Signal: Fast crosses above Slow
        if prev_fast <= prev_slow and current_fast > current_slow:
            return "BUY", price
        # Sell Signal: Fast crosses below Slow
        elif prev_fast >= prev_slow and current_fast < current_slow:
            return "SELL", price
        
        return None, price
    except Exception as e:
        print(f"Data error: {e}")
        return None, None

def is_market_open():
    now = datetime.now(TZ_NYC)
    # Market hours: 9:30 AM to 4:00 PM ET, Mon-Fri
    market_open = dt_time(9, 30)
    market_close = dt_time(16, 0)
    
    if now.weekday() >= 5: # Saturday/Sunday
        return False
    
    current_time = now.time()
    return market_open <= current_time <= market_close

def main():
    print(f"Starting NDX Tracker for {SYMBOL}...")
    print(f"Target: EMA {EMA_FAST}/{EMA_SLOW} Crossover")
    last_signal_time = None
    
    while True:
        if is_market_open():
            signal, price = get_signal()
            now_str = datetime.now(TZ_NYC).strftime("%H:%M:%S")
            
            if signal:
                direction = "🚀 *BUY*" if signal == "BUY" else "🔻 *SELL*"
                msg = f"{direction} Signal for {SYMBOL}\nPrice: ${price:.2f}\nTime: {now_str} ET"
                
                # Simple throttle to prevent multiple alerts for the same minute
                current_min = datetime.now().minute
                if last_signal_time != current_min:
                    send_telegram(msg)
                    print(f"[{now_str}] Signal Sent: {signal} at {price:.2f}")
                    last_signal_time = current_min
            else:
                p_str = f"${price:.2f}" if price is not None else "N/A"
                print(f"[{now_str}] Scanned {SYMBOL} at {p_str} - No Crossover")
            
            # Wait 60 seconds for the next candle
            time.sleep(60)
        else:
            now_nyc = datetime.now(TZ_NYC)
            print(f"[{now_nyc.strftime('%H:%M:%S')}] Market is closed. Waiting...")
            # Sleep longer when market is closed, check every 15 mins
            time.sleep(900)

if __name__ == "__main__":
    main()
