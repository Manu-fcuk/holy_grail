import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import time
from datetime import datetime
import market_data

# --- Page Config ---
st.set_page_config(
    page_title="Intraday Tracker",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Load CSS ---
def load_css(file_name):
    with open(file_name) as f:
        st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)

try:
    load_css("style.css")
except:
    pass 

# --- Sidebar Controls ---
st.sidebar.title("Configuration")
ticker_symbol = st.sidebar.text_input("Ticker Symbol", value="QQQ", help="QQQ is the ETF tracking Nasdaq 100.")
timeframe = st.sidebar.selectbox("Timeframe", ["1m", "2m", "5m", "15m", "30m", "1h"], index=0)

# Determine Period properly for yfinance to ensure enough data for indicators
period = "1d"
if timeframe in ["1m", "2m", "5m"]:
    period = "1d" 
elif timeframe in ["15m", "30m"]:
    period = "5d" # Need more data for 20/50 period SMAs/BBs
else:
    period = "1mo"

live_update = st.sidebar.checkbox("Live Updates (Every 60s)", value=True)

st.sidebar.markdown("---")
st.sidebar.markdown("## Strategy Selector")
strategy_mode = st.sidebar.radio(
    "Choose Signal Logic:",
    ("EMA Crossover", "RSI + Bollinger Reversion", "VWAP Trend", "ORB Strategy")
)

# Visibility Toggles
st.sidebar.markdown("### Chart Overlays")
show_ema = st.sidebar.checkbox("Show EMAs", value=(strategy_mode=="EMA Crossover"))
show_bb = st.sidebar.checkbox("Show Bollinger Bands", value=(strategy_mode=="RSI + Bollinger Reversion"))
show_vwap = st.sidebar.checkbox("Show VWAP", value=(strategy_mode=="VWAP Trend"))
show_orb = st.sidebar.checkbox("Show ORB Levels", value=(strategy_mode=="ORB Strategy"))

st.sidebar.markdown("---")
if strategy_mode == "EMA Crossover":
    st.sidebar.info("**EMA Crossover**: Trend Following.\n* **Buy**: EMA 9 > EMA 21\n* **Sell**: EMA 9 < EMA 21")
elif strategy_mode == "RSI + Bollinger Reversion":
    st.sidebar.info("**Mean Reversion**: Catching extremes.\n* **Buy**: Price < Lower BB & RSI < 30\n* **Sell**: Price > Upper BB & RSI > 70")
elif strategy_mode == "VWAP Trend":
    st.sidebar.info("**VWAP Trend**: Institutional Level.\n* **Buy**: Price > VWAP\n* **Sell**: Price < VWAP")
elif strategy_mode == "ORB Strategy":
    st.sidebar.info("**ORB (15m)**: Opening Range Breakout.\n* **Breakout**: First 15m Range.\n* **Buy**: Price > ORB High\n* **Sell**: Price < ORB Low")

# --- Notifications Setup ---
st.sidebar.markdown("---")
st.sidebar.markdown("## 🔔 Push Notifications")
enable_notifications = st.sidebar.checkbox("Enable Signal Alerts", value=False)
if enable_notifications:
    st.sidebar.write("To receive alerts, enter your Telegram details:")
    bot_token = st.sidebar.text_input("Bot Token", type="password")
    chat_id = st.sidebar.text_input("Chat ID")
    if bot_token and chat_id:
        st.sidebar.success("Telegram configured!")
    else:
        st.sidebar.info("Get your token from [@BotFather](https://t.me/botfather) and ID from [@userinfobot](https://t.me/userinfobot)")

# --- Main Logic ---

st.title(f"Nasdaq 100 Intraday - {strategy_mode}")
last_update_time = datetime.now().strftime("%H:%M:%S")
st.markdown(f"Tracking **{ticker_symbol}** on **{timeframe}** timeframe. | **Last Data Refresh:** {last_update_time}")

# Alert for Delay
if "^" in ticker_symbol and ticker_symbol != "^IXIC" and ticker_symbol != "^GSPC":
    st.warning(f"⚠️ **Note on {ticker_symbol}**: European and some other indices on Yahoo Finance are usually delayed by 15-20 minutes. Real-time data requires a paid API (e.g. Twelve Data or Broker API).")

chart_placeholder = st.empty()
metrics_placeholder = st.empty()
news_placeholder = st.empty()

def send_telegram_msg(token, chat_id, message):
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}
        requests.post(url, json=payload)
    except Exception as e:
        st.error(f"Telegram Error: {e}")

def render_dashboard():
    # 1. Fetch Data
    with st.spinner(f"Fetching data for {ticker_symbol}..."):
        df = market_data.get_stock_data(ticker_symbol, timeframe, period)
    
    if df is None or df.empty:
        st.error("No data found. Please check the ticker symbol or try a different timeframe.")
        return

    # 2. Calculate Signals
    df = market_data.calculate_signals(df)
    
    # Determine which signal column to use based on selection
    signal_col = 'Signal_EMA'
    if strategy_mode == "RSI + Bollinger Reversion":
        signal_col = 'Signal_RSI_BB'
    elif strategy_mode == "VWAP Trend":
        signal_col = 'Signal_VWAP'
    elif strategy_mode == "ORB Strategy":
        signal_col = 'Signal_ORB'
        
    # Safety Check: If for some reason the strategy column doesn't exist (e.g. not enough data for ORB), fallback to default scaling
    if signal_col not in df.columns:
        st.warning(f"Not enough data to calculate {strategy_mode} signals (e.g. today's market hasn't opened yet or data is missing). Showing chart without signals.")
        df[signal_col] = 0.0 # Create dummy column


    # Calculate Changes for Signals to plot markers (Triangles)
    # For State-based signals (EMA, VWAP, ORB), we check transitions (0 to 1, or -1 to 1)
    # For Pulse-based signals (RSI+BB), the signal itself is 1 or -1 only on the trigger candle
    
    if strategy_mode == "RSI + Bollinger Reversion":
        # These are pulses, not states, so we just filter where signal != 0
        buy_signals = df[df[signal_col] == 1]
        sell_signals = df[df[signal_col] == -1]
        current_state_val = df[signal_col].iloc[-1] # Likely 0
    else:
        # State transitions
        df['Position_Change'] = df[signal_col].diff()
        buy_signals = df[(df['Position_Change'] > 0) & (df[signal_col] == 1)]
        sell_signals = df[(df['Position_Change'] < 0) & (df[signal_col] == -1)]
        current_state_val = df[signal_col].iloc[-1]

    # --- Notification Trigger ---
    if enable_notifications and bot_token and chat_id:
        # Check if the very last candle triggered a new signal
        last_signal = 0
        if strategy_mode == "RSI + Bollinger Reversion":
            last_signal = current_state_val # It's a pulse
        else:
            # Check if position change happened on the last candle
            if df['Position_Change'].iloc[-1] != 0:
                last_signal = current_state_val
        
        if last_signal != 0:
            direction = "🚀 BUY" if last_signal == 1 else "🔻 SELL"
            msg = f"*{direction} Signal* for {ticker_symbol}\n" \
                  f"Strategy: {strategy_mode}\n" \
                  f"Price: ${latest_close:.2f}\n" \
                  f"Time: {datetime.now().strftime('%H:%M:%S')}"
            
            # Use session state to avoid duplicate messages on every rerun if signal persists
            # (Though for pulses it's fine, for states we only want the transition)
            alert_key = f"alert_{ticker_symbol}_{last_signal}_{df.index[-1]}"
            if alert_key not in st.session_state:
                send_telegram_msg(bot_token, chat_id, msg)
                st.session_state[alert_key] = True
                st.toast(f"Telegram Alert Sent: {direction}!", icon="🔔")

    # Metrics
    latest_close = df['Close'].iloc[-1]
    last_price = df['Close'].iloc[-2] if len(df) > 1 else latest_close
    price_change = latest_close - last_price
    pct_change = (price_change / last_price) * 100
    
    current_signal_text = "N/A"
    signal_color = "off"
    
    # Logic for current Trend/Signal Display
    if strategy_mode == "RSI + Bollinger Reversion":
        if current_state_val == 1:
            current_signal_text = "BUY NOW"
            signal_color = "normal"
        elif current_state_val == -1:
            current_signal_text = "SELL NOW"
            signal_color = "inverse"
        else:
            current_signal_text = "WAIT"
    else:
        if current_state_val == 1:
            current_signal_text = "BULLISH"
            signal_color = "normal"
        elif current_state_val == -1:
            current_signal_text = "BEARISH"
            signal_color = "inverse"

    with metrics_placeholder.container():
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Current Price", f"${latest_close:.2f}", f"{price_change:.2f} ({pct_change:.2f}%)")
        col2.metric("Strategy Signal", current_signal_text, delta_color=signal_color)
        col3.metric("RSI (14)", f"{df['RSI'].iloc[-1]:.1f}")
        col4.metric("Last Updated", datetime.now().strftime("%H:%M:%S"))

    # 3. Charting
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, 
                        vertical_spacing=0.05, row_heights=[0.7, 0.3],
                        subplot_titles=(f"{ticker_symbol} Price", "RSI"))

    # Candlestick
    fig.add_trace(go.Candlestick(x=df.index,
                                 open=df['Open'], high=df['High'],
                                 low=df['Low'], close=df['Close'],
                                 name="Price"), row=1, col=1)

    # Overlays
    if show_ema:
        fig.add_trace(go.Scatter(x=df.index, y=df['EMA_9'], line=dict(color='#2962FF', width=1), name="EMA 9"), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['EMA_21'], line=dict(color='#EF5350', width=1), name="EMA 21"), row=1, col=1)

    if show_bb:
        fig.add_trace(go.Scatter(x=df.index, y=df['BB_High'], line=dict(color='rgba(255, 255, 255, 0.3)', width=1, dash='dot'), name="BB Upper"), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['BB_Low'], line=dict(color='rgba(255, 255, 255, 0.3)', width=1, dash='dot'), name="BB Lower"), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['BB_Mid'], line=dict(color='rgba(255, 255, 255, 0.5)', width=1), name="BB Mid"), row=1, col=1)

    if show_vwap:
        fig.add_trace(go.Scatter(x=df.index, y=df['VWAP'], line=dict(color='#FFD700', width=2), name="VWAP"), row=1, col=1)
        
    if show_orb:
        # Plot ORB Levels for the current day
        # Only plot where they are defined (not None) to avoid plotting 0.0 or messing up scale
        if 'ORB_High' in df.columns:
            fig.add_trace(go.Scatter(x=df.index, y=df['ORB_High'], line=dict(color='#00E676', width=2, dash='dash'), name="ORB High"), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['ORB_Low'], line=dict(color='#FF1744', width=2, dash='dash'), name="ORB Low"), row=1, col=1)

    # Markers (Buy/Sell)
    if not buy_signals.empty:
        fig.add_trace(go.Scatter(x=buy_signals.index, y=buy_signals['Low'] * 0.999,
                                 mode='markers', marker=dict(symbol='triangle-up', color='#00C853', size=14),
                                 name="BUY Signal"), row=1, col=1)
    
    if not sell_signals.empty:
        fig.add_trace(go.Scatter(x=sell_signals.index, y=sell_signals['High'] * 1.001,
                                 mode='markers', marker=dict(symbol='triangle-down', color='#D50000', size=14),
                                 name="SELL Signal"), row=1, col=1)

    # RSI Subplot
    fig.add_trace(go.Scatter(x=df.index, y=df['RSI'], line=dict(color='#BA68C8', width=2), name="RSI"), row=2, col=1)
    fig.add_shape(type="line", x0=df.index[0], x1=df.index[-1], y0=70, y1=70, line=dict(color="red", width=1, dash="dash"), row=2, col=1)
    fig.add_shape(type="line", x0=df.index[0], x1=df.index[-1], y0=30, y1=30, line=dict(color="green", width=1, dash="dash"), row=2, col=1)

    fig.update_layout(
        height=700,
        margin=dict(l=10, r=10, t=30, b=10),
        template="plotly_dark",
        xaxis_rangeslider_visible=False,
        hovermode='x unified',
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    
    chart_placeholder.plotly_chart(fig, use_container_width=True)

    # 5. News & Sentiment
    with news_placeholder.container():
        st.markdown("### 📰 Latest News & Sentiment")
        SENT_COLORS = {"Positive": "#00C853", "Negative": "#D50000", "Neutral": "#FFAB00"}
        SENT_EMOJIS = {"Positive": "🟢", "Negative": "🔴", "Neutral": "🟡"}
        with st.spinner("Fetching latest news..."):
            news_df = market_data.get_news_sentiment(ticker_symbol)
        if not news_df.empty:
            avg_sentiment = news_df['score'].mean()
            sent_text = "Neutral ⚖️"
            sent_color = "#FFAB00"
            if avg_sentiment > 0.05:
                sent_text = "Positive 📈"
                sent_color = "#00C853"
            elif avg_sentiment < -0.05:
                sent_text = "Negative 📉"
                sent_color = "#D50000"
            pct = min(max((avg_sentiment + 1) / 2 * 100, 0), 100)
            st.markdown(
                f"<div style='margin-bottom:12px;'><b>Overall Sentiment:</b> "
                f"<span style='color:{sent_color};font-weight:bold;font-size:1.1em;'> {sent_text}</span>"
                f" &nbsp;&nbsp;(Score: {avg_sentiment:.2f} | {len(news_df)} articles)</div>"
                f"<div style='background:#1e2228;border-radius:8px;height:10px;margin-bottom:18px;'>"
                f"<div style='background:{sent_color};width:{pct:.0f}%;height:10px;border-radius:8px;'></div></div>",
                unsafe_allow_html=True
            )
            for _, row in news_df.head(12).iterrows():
                s = row.get('sentiment', 'Neutral')
                badge_color = SENT_COLORS.get(s, "#FFAB00")
                emoji = SENT_EMOJIS.get(s, "🟡")
                st.markdown(
                    f"<div style='background:#161b22;border-left:4px solid {badge_color};"
                    f"padding:10px 14px;margin-bottom:8px;border-radius:6px;'>"
                    f"<div style='font-size:0.8em;color:{badge_color};margin-bottom:3px;'>"
                    f"{emoji} <b>{s}</b> &nbsp;|&nbsp; {row.get('publisher','N/A')} &nbsp;|&nbsp; {row.get('published','N/A')}</div>"
                    f"<a href='{row.get('link','#')}' target='_blank' style='color:#e6edf3;text-decoration:none;font-weight:bold;'>"
                    f"{row.get('title','No title')}</a></div>",
                    unsafe_allow_html=True
                )
        else:
            st.info("No recent news found. Try a different ticker or check your connection.")



render_dashboard()

if live_update:
    time.sleep(60)
    st.rerun()