"""
================================================================
BTC SCALPING BOT - ULTRA AGGRESSIVE
================================================================
Strategies used:
1. EMA 3/8 Crossover (fast scalping)
2. RSI Divergence (momentum)
3. Bollinger Bands (breakout)
4. Volume Spike (confirmation)
5. VWAP (price direction)

Har 1 minute mein check karta hai
Target: 0.3-0.8% per trade
Stop Loss: 0.2%
Risk:Reward = 1:3
================================================================
"""

import requests
import time
import logging
import os
import statistics
from datetime import datetime
from collections import deque

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s'
)
logger = logging.getLogger(__name__)

# ================================================================
# SETTINGS
# ================================================================
BOT_URL        = os.getenv("BOT_URL", "https://trading-bot-1-7hab.onrender.com")
BOT_SECRET     = os.getenv("WEBHOOK_SECRET", "MeraBotSecret123")
SYMBOL         = "BTCUSD"
CHECK_SECONDS  = 60       # Har 1 minute mein check
MIN_CONFIDENCE = 2        # Minimum 2 strategies agree karein

# Scalping targets
STOP_LOSS_PCT  = 0.002    # 0.2% stop loss
TAKE_PROFIT_PCT= 0.006    # 0.6% take profit (3:1 RR)

# ================================================================
# DATA STORAGE
# ================================================================
prices  = deque(maxlen=100)   # Last 100 prices
volumes = deque(maxlen=100)   # Last 100 volumes
highs   = deque(maxlen=20)
lows    = deque(maxlen=20)

trade_stats = {
    "total_signals": 0,
    "buy_signals": 0,
    "sell_signals": 0,
    "last_signal": None,
    "last_signal_time": None,
    "start_time": datetime.now().isoformat()
}

# ================================================================
# LIVE DATA — Binance free API (most accurate for BTC)
# ================================================================
def get_btc_data():
    """Binance se live BTC OHLCV data lo — bilkul free"""
    try:
        # 1 minute candles
        url = "https://api.binance.com/api/v3/klines"
        params = {
            "symbol": "BTCUSDT",
            "interval": "1m",
            "limit": 50
        }
        res = requests.get(url, params=params, timeout=10)
        candles = res.json()

        if not candles or isinstance(candles, dict):
            raise Exception("Bad response")

        ohlcv = []
        for c in candles:
            ohlcv.append({
                "open":   float(c[1]),
                "high":   float(c[2]),
                "low":    float(c[3]),
                "close":  float(c[4]),
                "volume": float(c[5])
            })

        return ohlcv

    except Exception as e:
        logger.error(f"Binance error: {e}")
        # Fallback — CoinGecko
        try:
            url = "https://api.coingecko.com/api/v3/simple/price"
            params = {"ids": "bitcoin", "vs_currencies": "usd"}
            res = requests.get(url, params=params, timeout=10)
            price = float(res.json()["bitcoin"]["usd"])
            return [{"open": price, "high": price, "low": price,
                    "close": price, "volume": 100}]
        except:
            return None

# ================================================================
# TECHNICAL INDICATORS
# ================================================================
def ema(data, period):
    if len(data) < period:
        return data[-1] if data else 0
    mult = 2 / (period + 1)
    result = sum(data[:period]) / period
    for val in data[period:]:
        result = (val - result) * mult + result
    return round(result, 2)

def rsi(closes, period=14):
    if len(closes) < period + 1:
        return 50
    gains, losses = [], []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i-1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))
    avg_g = sum(gains[-period:]) / period
    avg_l = sum(losses[-period:]) / period
    if avg_l == 0:
        return 100
    return round(100 - (100 / (1 + avg_g/avg_l)), 2)

def bollinger_bands(closes, period=20, std_mult=2.0):
    if len(closes) < period:
        mid = closes[-1]
        return mid, mid * 1.01, mid * 0.99
    recent = list(closes)[-period:]
    mid = sum(recent) / period
    std = statistics.stdev(recent)
    return round(mid, 2), round(mid + std*std_mult, 2), round(mid - std*std_mult, 2)

def vwap(closes_list, volumes_list):
    if len(closes_list) < 2:
        return closes_list[-1] if closes_list else 0
    tp_vol = sum(c * v for c, v in zip(closes_list, volumes_list))
    total_vol = sum(volumes_list)
    return round(tp_vol / total_vol, 2) if total_vol > 0 else closes_list[-1]

def volume_spike(volumes_list):
    if len(volumes_list) < 10:
        return False
    avg = sum(list(volumes_list)[-20:-1]) / min(19, len(volumes_list)-1)
    latest = list(volumes_list)[-1]
    return latest > avg * 1.5  # 50% above average

# ================================================================
# SCALPING SIGNAL ENGINE — 5 Strategies
# ================================================================
def analyze_scalp_signal(ohlcv):
    """
    5 strategies check karo
    2+ agree karein toh trade karo
    """
    if len(ohlcv) < 22:
        logger.info(f"Data collect ho raha hai: {len(ohlcv)}/22")
        return None, 0, 0, []

    closes  = [c["close"]  for c in ohlcv]
    vols    = [c["volume"] for c in ohlcv]
    highs_l = [c["high"]   for c in ohlcv]
    lows_l  = [c["low"]    for c in ohlcv]

    price   = closes[-1]
    signals = {"buy": [], "sell": []}

    # ── Strategy 1: EMA 3/8 Crossover (Ultra Fast Scalp) ──
    e3      = ema(closes, 3)
    e8      = ema(closes, 8)
    e3_prev = ema(closes[:-1], 3)
    e8_prev = ema(closes[:-1], 8)

    if e3_prev <= e8_prev and e3 > e8:
        signals["buy"].append("EMA3/8 Crossover UP")
    elif e3_prev >= e8_prev and e3 < e8:
        signals["sell"].append("EMA3/8 Crossover DOWN")

    # ── Strategy 2: RSI Scalp (Extreme levels) ──
    rsi_val = rsi(closes, 7)   # Fast RSI

    if rsi_val < 35:
        signals["buy"].append(f"RSI Oversold ({rsi_val})")
    elif rsi_val > 65:
        signals["sell"].append(f"RSI Overbought ({rsi_val})")

    # ── Strategy 3: Bollinger Band Bounce ──
    bb_mid, bb_upper, bb_lower = bollinger_bands(closes, 15)

    if price <= bb_lower * 1.001:
        signals["buy"].append(f"BB Lower Bounce (${bb_lower:,.0f})")
    elif price >= bb_upper * 0.999:
        signals["sell"].append(f"BB Upper Rejection (${bb_upper:,.0f})")

    # ── Strategy 4: Volume Spike Confirmation ──
    vol_spike = volume_spike(vols)
    if vol_spike:
        if e3 > e8:
            signals["buy"].append("Volume Spike BUY")
        else:
            signals["sell"].append("Volume Spike SELL")

    # ── Strategy 5: VWAP Direction ──
    vwap_val = vwap(closes[-20:], vols[-20:])

    if price > vwap_val * 1.0005 and e3 > e8:
        signals["buy"].append(f"Above VWAP (${vwap_val:,.0f})")
    elif price < vwap_val * 0.9995 and e3 < e8:
        signals["sell"].append(f"Below VWAP (${vwap_val:,.0f})")

    # ── Decision ──
    buy_count  = len(signals["buy"])
    sell_count = len(signals["sell"])

    logger.info(f"Price: ${price:,.2f} | EMA3: ${e3:,.0f} | EMA8: ${e8:,.0f} | RSI: {rsi_val} | BB: {bb_lower:,.0f}/{bb_upper:,.0f}")
    logger.info(f"BUY signals: {buy_count} | SELL signals: {sell_count}")

    if buy_count >= MIN_CONFIDENCE and buy_count > sell_count:
        return "buy", rsi_val, price, signals["buy"]
    elif sell_count >= MIN_CONFIDENCE and sell_count > buy_count:
        return "sell", rsi_val, price, signals["sell"]
    else:
        return "hold", rsi_val, price, []

# ================================================================
# SIGNAL SENDER
# ================================================================
def send_signal(action, price, rsi_val, reasons):
    """Bot ko signal bhejo"""
    try:
        stop_loss   = round(price * (1 - STOP_LOSS_PCT), 2)  if action == "buy"  else round(price * (1 + STOP_LOSS_PCT), 2)
        take_profit = round(price * (1 + TAKE_PROFIT_PCT), 2) if action == "buy" else round(price * (1 - TAKE_PROFIT_PCT), 2)

        payload = {
            "action":      action,
            "symbol":      SYMBOL,
            "price":       str(price),
            "rsi":         str(rsi_val),
            "strategy":    "SCALPING_5X",
            "timeframe":   "1m",
            "reasons":     ", ".join(reasons),
            "stop_loss":   str(stop_loss),
            "take_profit": str(take_profit)
        }

        res = requests.post(
            f"{BOT_URL}/webhook",
            json=payload,
            headers={
                "Content-Type":    "application/json",
                "x-webhook-secret": BOT_SECRET
            },
            timeout=30
        )

        result = res.json()
        trade_stats["total_signals"] += 1
        trade_stats["last_signal"]   = action
        trade_stats["last_signal_time"] = datetime.now().isoformat()

        if action == "buy":
            trade_stats["buy_signals"] += 1
        else:
            trade_stats["sell_signals"] += 1

        logger.info(f"Bot response: {result}")
        return result

    except Exception as e:
        logger.error(f"Send error: {e}")
        return None

# ================================================================
# ANTI-SPAM — Same signal bar bar nahi
# ================================================================
last_action    = None
last_action_time = 0
COOLDOWN_SECONDS = 300   # 5 minute cooldown same signal ke liye

# ================================================================
# MAIN LOOP
# ================================================================
def main():
    global last_action, last_action_time

    logger.info("=" * 55)
    logger.info("BTC SCALPING BOT - ULTRA AGGRESSIVE")
    logger.info(f"Bot URL:    {BOT_URL}")
    logger.info(f"Symbol:     {SYMBOL}")
    logger.info(f"Check:      Har {CHECK_SECONDS} second")
    logger.info(f"Stop Loss:  {STOP_LOSS_PCT*100}%")
    logger.info(f"Take Profit:{TAKE_PROFIT_PCT*100}%")
    logger.info(f"Min Signals:{MIN_CONFIDENCE}/5 strategies")
    logger.info("=" * 55)

    iteration = 0

    while True:
        iteration += 1
        now = datetime.now().strftime("%H:%M:%S")

        try:
            logger.info(f"\n{'='*40}")
            logger.info(f"[#{iteration}] [{now}] BTC Check kar raha hoon...")

            # Data lo
            ohlcv = get_btc_data()
            if not ohlcv:
                logger.warning("Data nahi mila — 30 sec wait")
                time.sleep(30)
                continue

            # Signal analyze karo
            action, rsi_val, price, reasons = analyze_scalp_signal(ohlcv)

            if action and action != "hold":
                now_ts = time.time()
                cooldown_ok = (
                    last_action != action or
                    (now_ts - last_action_time) > COOLDOWN_SECONDS
                )

                if cooldown_ok:
                    logger.info(f"SCALP SIGNAL: {action.upper()} @ ${price:,.2f}")
                    logger.info(f"Reasons: {', '.join(reasons)}")

                    result = send_signal(action, price, rsi_val, reasons)

                    if result:
                        last_action      = action
                        last_action_time = now_ts
                        logger.info(f"Signal bhej diya: {action.upper()} @ ${price:,.2f}")
                else:
                    remaining = int(COOLDOWN_SECONDS - (now_ts - last_action_time))
                    logger.info(f"Cooldown: {remaining}s baaki ({action} recently hua)")

            else:
                logger.info(f"HOLD | Price: ${price:,.2f} | RSI: {rsi_val}")

            # Stats har 10 iteration pe
            if iteration % 10 == 0:
                logger.info(f"\nSTATS: Total={trade_stats['total_signals']} | BUY={trade_stats['buy_signals']} | SELL={trade_stats['sell_signals']}")

            time.sleep(CHECK_SECONDS)

        except KeyboardInterrupt:
            logger.info("\nBot band kar diya")
            logger.info(f"Final Stats: {trade_stats}")
            break
        except Exception as e:
            logger.error(f"Loop error: {e}")
            time.sleep(30)

if __name__ == "__main__":
    main()
