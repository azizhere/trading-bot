"""
================================================================
BTC SCALPING BOT - ULTRA AGGRESSIVE (FIXED)
Alpaca API use karta hai — price aur trading dono
CoinGecko fallback bhi hai
================================================================
"""

import requests
import time
import logging
import os
import statistics
from datetime import datetime
from collections import deque

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
logger = logging.getLogger(__name__)

# ================================================================
# SETTINGS
# ================================================================
BOT_URL         = os.getenv("BOT_URL",          "https://trading-bot-1-7hab.onrender.com")
BOT_SECRET      = os.getenv("WEBHOOK_SECRET",    "MeraBotSecret123")
ALPACA_KEY      = os.getenv("ALPACA_API_KEY",    "")
ALPACA_SECRET   = os.getenv("ALPACA_SECRET_KEY", "")

SYMBOL          = "BTCUSD"
CHECK_SECONDS   = 60
MIN_CONFIDENCE  = 2
STOP_LOSS_PCT   = 0.002
TAKE_PROFIT_PCT = 0.006
COOLDOWN        = 300

prices = deque(maxlen=100)
trade_stats = {"total":0,"buys":0,"sells":0,"last_signal":None,"last_time":0}

# ================================================================
# PRICE — Alpaca first, CoinGecko fallback
# ================================================================
def get_btc_price():
    # Try Alpaca first
    if ALPACA_KEY and ALPACA_SECRET:
        try:
            url = "https://data.alpaca.markets/v1beta3/crypto/us/latest/quotes"
            headers = {
                "APCA-API-KEY-ID": ALPACA_KEY,
                "APCA-API-SECRET-KEY": ALPACA_SECRET
            }
            res  = requests.get(url, headers=headers, params={"symbols":"BTC/USD"}, timeout=15)
            data = res.json()
            quote = data["quotes"]["BTC/USD"]
            price = (float(quote["bp"]) + float(quote["ap"])) / 2
            logger.info(f"BTC (Alpaca): ${price:,.2f}")
            return round(price, 2)
        except Exception as e:
            logger.warning(f"Alpaca price failed: {e} — CoinGecko try kar raha hoon")

    # Fallback CoinGecko
    try:
        res   = requests.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={"ids":"bitcoin","vs_currencies":"usd"},
            timeout=15
        )
        price = float(res.json()["bitcoin"]["usd"])
        logger.info(f"BTC (CoinGecko): ${price:,.2f}")
        return price
    except Exception as e:
        logger.error(f"Price error: {e}")
        return None

# ================================================================
# INDICATORS
# ================================================================
def calc_ema(data, period):
    data = list(data)
    if len(data) < period:
        return data[-1] if data else 0
    mult = 2/(period+1)
    val  = sum(data[:period])/period
    for p in data[period:]:
        val = (p-val)*mult+val
    return round(val, 2)

def calc_rsi(closes, period=7):
    closes = list(closes)
    if len(closes) < period+1:
        return 50
    g,l = [],[]
    for i in range(1,len(closes)):
        d = closes[i]-closes[i-1]
        g.append(max(d,0)); l.append(max(-d,0))
    ag = sum(g[-period:])/period
    al = sum(l[-period:])/period
    return round(100-(100/(1+ag/al)),2) if al else 100

def calc_bb(closes, period=15):
    closes = list(closes)
    if len(closes) < period:
        m=closes[-1]; return m,m*1.01,m*0.99
    r   = closes[-period:]
    mid = sum(r)/period
    std = statistics.stdev(r) if len(r)>1 else 0
    return round(mid,2), round(mid+std*2,2), round(mid-std*2,2)

def calc_momentum(closes, period=5):
    closes = list(closes)
    if len(closes) < period+1:
        return 0
    return round((closes[-1]-closes[-period-1])/closes[-period-1]*100, 3)

# ================================================================
# SIGNAL ENGINE
# ================================================================
def analyze(price_list):
    closes = list(price_list)
    if len(closes) < 10:
        logger.info(f"Data jama ho raha hai: {len(closes)}/10")
        return "hold", 50, closes[-1] if closes else 0, []

    current = closes[-1]
    buy_s, sell_s = [], []

    # 1. EMA 3/8
    e3=calc_ema(closes,3); e8=calc_ema(closes,8)
    e3p=calc_ema(closes[:-1],3); e8p=calc_ema(closes[:-1],8)
    if e3p<=e8p and e3>e8: buy_s.append("EMA3/8 Cross UP")
    elif e3p>=e8p and e3<e8: sell_s.append("EMA3/8 Cross DOWN")

    # 2. RSI
    rsi_val=calc_rsi(closes,7)
    if rsi_val<35: buy_s.append(f"RSI Oversold ({rsi_val})")
    elif rsi_val>65: sell_s.append(f"RSI Overbought ({rsi_val})")

    # 3. Bollinger Bands
    _,bb_up,bb_dn=calc_bb(closes,15)
    if current<=bb_dn*1.001: buy_s.append("BB Lower Bounce")
    elif current>=bb_up*0.999: sell_s.append("BB Upper Reject")

    # 4. Momentum
    mom=calc_momentum(closes,5)
    if mom>0.15: buy_s.append(f"Momentum UP ({mom}%)")
    elif mom<-0.15: sell_s.append(f"Momentum DOWN ({mom}%)")

    # 5. EMA Trend
    e21=calc_ema(closes,21) if len(closes)>=21 else e8
    if e8>e21 and current>e8: buy_s.append("Uptrend")
    elif e8<e21 and current<e8: sell_s.append("Downtrend")

    logger.info(f"Price:${current:,.2f} | RSI:{rsi_val} | BB:{bb_dn:,.0f}/{bb_up:,.0f} | Mom:{mom}%")
    logger.info(f"BUY:{len(buy_s)} signals | SELL:{len(sell_s)} signals")

    if len(buy_s)>=MIN_CONFIDENCE and len(buy_s)>len(sell_s):
        return "buy", rsi_val, current, buy_s
    elif len(sell_s)>=MIN_CONFIDENCE and len(sell_s)>len(buy_s):
        return "sell", rsi_val, current, sell_s
    return "hold", rsi_val, current, []

# ================================================================
# SEND TO BOT
# ================================================================
def send_signal(action, price, rsi_val, reasons):
    try:
        sl = round(price*(1-STOP_LOSS_PCT),2) if action=="buy" else round(price*(1+STOP_LOSS_PCT),2)
        tp = round(price*(1+TAKE_PROFIT_PCT),2) if action=="buy" else round(price*(1-TAKE_PROFIT_PCT),2)

        res = requests.post(
            f"{BOT_URL}/webhook",
            json={"action":action,"symbol":SYMBOL,"price":str(price),
                  "rsi":str(rsi_val),"strategy":"SCALPING_5X","timeframe":"1m",
                  "reasons":", ".join(reasons),"stop_loss":str(sl),"take_profit":str(tp)},
            headers={"Content-Type":"application/json","x-webhook-secret":BOT_SECRET},
            timeout=30
        )
        result = res.json()
        trade_stats["total"]+=1
        trade_stats["last_signal"]=action
        trade_stats["last_time"]=time.time()
        if action=="buy": trade_stats["buys"]+=1
        else: trade_stats["sells"]+=1
        logger.info(f"Bot response: {result}")
        return result
    except Exception as e:
        logger.error(f"Send error: {e}")
        return None

# ================================================================
# MAIN
# ================================================================
def main():
    logger.info("="*55)
    logger.info("BTC SCALPING BOT - ULTRA AGGRESSIVE (FIXED)")
    logger.info(f"Bot:        {BOT_URL}")
    logger.info(f"Symbol:     {SYMBOL}")
    logger.info(f"Check:      Har {CHECK_SECONDS}s")
    logger.info(f"SL/TP:      {STOP_LOSS_PCT*100}% / {TAKE_PROFIT_PCT*100}%")
    logger.info(f"Min Signals:{MIN_CONFIDENCE}/5")
    logger.info("="*55)

    iteration=0
    while True:
        iteration+=1
        try:
            logger.info(f"\n--- #{iteration} [{datetime.now().strftime('%H:%M:%S')}] ---")
            price = get_btc_price()
            if not price:
                time.sleep(30); continue

            prices.append(price)
            action, rsi_val, current, reasons = analyze(prices)

            if action != "hold":
                now_ts = time.time()
                if trade_stats["last_signal"]!=action or (now_ts-trade_stats["last_time"])>COOLDOWN:
                    logger.info(f"SIGNAL: {action.upper()} @ ${current:,.2f} | {', '.join(reasons)}")
                    send_signal(action, current, rsi_val, reasons)
                else:
                    left=int(COOLDOWN-(now_ts-trade_stats["last_time"]))
                    logger.info(f"Cooldown: {left}s baaki")
            else:
                logger.info(f"HOLD | ${current:,.2f} | RSI:{rsi_val}")

            if iteration%10==0:
                logger.info(f"STATS: Total={trade_stats['total']} BUY={trade_stats['buys']} SELL={trade_stats['sells']}")

            time.sleep(CHECK_SECONDS)

        except KeyboardInterrupt:
            logger.info("Band ho raha hai...")
            break
        except Exception as e:
            logger.error(f"Error: {e}")
            time.sleep(30)

if __name__=="__main__":
    main()