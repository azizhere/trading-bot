# ================================================================
# SUPER AGGRESSIVE PRO MAX TRADING BOT v1.0
# By: Claude (Anthropic) + Your Strategy
# ================================================================
# SETUP:
# 1. pip install -r requirements.txt
# 2. .env file banao (neeche dekho)
# 3. uvicorn main:app --reload
# ================================================================

from fastapi import FastAPI, Request, HTTPException, Header
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import alpaca_trade_api as tradeapi
from dotenv import load_dotenv
import os, json, logging, time
from datetime import datetime, timedelta
from typing import Optional
import anthropic

load_dotenv()

# ================================================================
# LOGGING SETUP - Har cheez record hogi
# ================================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    handlers=[
        logging.FileHandler('trading_bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Super Aggressive Pro Max Bot 🔥", version="3.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ================================================================
# BROKER CONNECTION
# ⚠️ .env file mein yeh daalo:
#
# ALPACA_API_KEY=your_key_here
# ALPACA_SECRET_KEY=your_secret_here
# ANTHROPIC_API_KEY=sk-ant-your_key_here
# WEBHOOK_SECRET=any_strong_password
# PAPER_TRADING=true
# ================================================================

PAPER = os.getenv("PAPER_TRADING", "true").lower() == "true"
BASE_URL = "https://paper-api.alpaca.markets" if PAPER else "https://api.alpaca.markets"

alpaca = tradeapi.REST(
    key_id=os.getenv("ALPACA_API_KEY"),
    secret_key=os.getenv("ALPACA_SECRET_KEY"),
    base_url=BASE_URL,
    api_version='v2'
)

claude_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "changeme123")

# ================================================================
# SUPER AGGRESSIVE RISK SETTINGS
# Paper trading mein sab test hoga — real mein tab jaoge
# ================================================================
RISK_CONFIG = {
    # Aggressive Settings
    "risk_per_trade_pct": 0.05,        # 5% per trade (aggressive)
    "max_leverage": 4,                  # 4x leverage
    "max_open_positions": 5,            # 5 positions ek saath
    "max_daily_loss_pct": 0.10,        # 10% daily max loss
    "max_drawdown_pct": 0.20,          # 20% max drawdown
    "stop_loss_pct": 0.03,             # 3% stop loss
    "take_profit_rr": 3.0,             # 3:1 Risk:Reward
    "min_ai_confidence": 65,           # Claude ka min 65% confidence chahiye
    "trailing_stop": True,             # Trailing stop loss
    "pyramid_entries": True,           # Winning trades mein add karo
}

# ================================================================
# TRADE HISTORY (memory ke liye)
# ================================================================
trade_history = []
daily_stats = {
    "date": datetime.now().date().isoformat(),
    "trades": 0,
    "wins": 0,
    "losses": 0,
    "pnl": 0.0,
    "start_balance": None
}

# ================================================================
# RISK MANAGER CLASS
# ================================================================
class SuperAggressiveRiskManager:
    def __init__(self, config):
        self.config = config
        self.peak_balance = None

    def get_account(self):
        try:
            acc = alpaca.get_account()
            positions = alpaca.list_positions()
            balance = float(acc.cash)
            portfolio = float(acc.portfolio_value)
            equity = float(acc.equity)
            last_equity = float(acc.last_equity)

            if daily_stats["start_balance"] is None:
                daily_stats["start_balance"] = equity

            return {
                "balance": balance,
                "portfolio_value": portfolio,
                "equity": equity,
                "daily_pnl": equity - last_equity,
                "daily_pnl_pct": (equity - last_equity) / last_equity * 100,
                "open_positions": len(positions),
                "positions": positions,
                "buying_power": float(acc.buying_power)
            }
        except Exception as e:
            logger.error(f"Account error: {e}")
            return None

    def check_all_risks(self, account):
        """Saare risk checks ek jagah"""
        checks = []

        # 1. Daily loss check
        daily_loss_pct = abs(account["daily_pnl_pct"]) / 100
        if account["daily_pnl"] < 0 and daily_loss_pct >= self.config["max_daily_loss_pct"]:
            checks.append(f"DAILY LOSS LIMIT: {daily_loss_pct:.1%} >= {self.config['max_daily_loss_pct']:.1%}")

        # 2. Drawdown check
        if self.peak_balance is None:
            self.peak_balance = account["equity"]
        self.peak_balance = max(self.peak_balance, account["equity"])
        drawdown = (self.peak_balance - account["equity"]) / self.peak_balance
        if drawdown >= self.config["max_drawdown_pct"]:
            checks.append(f"MAX DRAWDOWN: {drawdown:.1%} >= {self.config['max_drawdown_pct']:.1%}")

        # 3. Max positions check
        if account["open_positions"] >= self.config["max_open_positions"]:
            checks.append(f"MAX POSITIONS: {account['open_positions']} open")

        return checks  # Empty = all clear

    def calculate_position(self, account, entry_price, action):
        """Aggressive position size"""
        equity = account["equity"]
        risk_amount = equity * self.config["risk_per_trade_pct"]

        stop_distance = entry_price * self.config["stop_loss_pct"]
        base_qty = risk_amount / stop_distance

        # Leverage apply karo
        qty = base_qty * self.config["max_leverage"]

        # Stop loss & take profit
        if action == "buy":
            stop_loss = round(entry_price * (1 - self.config["stop_loss_pct"]), 4)
            take_profit = round(entry_price + (stop_distance * self.config["take_profit_rr"] * self.config["max_leverage"]), 4)
        else:
            stop_loss = round(entry_price * (1 + self.config["stop_loss_pct"]), 4)
            take_profit = round(entry_price - (stop_distance * self.config["take_profit_rr"] * self.config["max_leverage"]), 4)

        return {
            "qty": round(qty, 4),
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "risk_amount": risk_amount,
            "potential_profit": risk_amount * self.config["take_profit_rr"] * self.config["max_leverage"]
        }

risk_manager = SuperAggressiveRiskManager(RISK_CONFIG)

# ================================================================
# CLAUDE AI - SUPER INTELLIGENT ANALYSIS
# ================================================================
def claude_deep_analysis(signal, account, position_plan):
    """
    Claude ko deep market analysis ke liye bhejte hain.
    Yeh sirf approve/reject nahi karta — poora analysis karta hai.
    """
    prompt = f"""
You are an elite algorithmic trading AI with expertise in technical analysis, 
market microstructure, and risk management. Analyze this trade signal AGGRESSIVELY 
but INTELLIGENTLY.

═══════════════════════════════════
TRADE SIGNAL
═══════════════════════════════════
Action: {signal.get('action', '').upper()}
Symbol: {signal.get('symbol')}
Price: ${signal.get('price')}
RSI: {signal.get('rsi', 'N/A')}
MACD: {signal.get('macd', 'N/A')}
Volume: {signal.get('volume', 'N/A')}
Trend: {signal.get('trend', 'N/A')}
Signal Strength: {signal.get('strength', 'N/A')}
Timeframe: {signal.get('timeframe', '15m')}
Strategy: {signal.get('strategy', 'MA Crossover')}

═══════════════════════════════════
ACCOUNT STATUS
═══════════════════════════════════
Equity: ${account.get('equity', 0):.2f}
Daily P&L: ${account.get('daily_pnl', 0):.2f} ({account.get('daily_pnl_pct', 0):.2f}%)
Open Positions: {account.get('open_positions', 0)}
Buying Power: ${account.get('buying_power', 0):.2f}

═══════════════════════════════════
POSITION PLAN
═══════════════════════════════════
Quantity: {position_plan.get('qty')}
Stop Loss: ${position_plan.get('stop_loss')}
Take Profit: ${position_plan.get('take_profit')}
Risk Amount: ${position_plan.get('risk_amount', 0):.2f}
Potential Profit: ${position_plan.get('potential_profit', 0):.2f}

═══════════════════════════════════
YOUR ANALYSIS TASK
═══════════════════════════════════
1. Is this signal strong? (technical confluence)
2. Is the risk:reward acceptable?
3. Are there any RED FLAGS?
4. Should we take this trade?

RESPOND ONLY IN THIS EXACT JSON FORMAT:
{{
  "approved": true/false,
  "confidence": 0-100,
  "signal_quality": "STRONG/MEDIUM/WEAK",
  "key_reason": "main reason in one line",
  "red_flags": ["flag1", "flag2"],
  "entry_advice": "any entry timing advice",
  "risk_assessment": "LOW/MEDIUM/HIGH/EXTREME"
}}
"""

    try:
        response = claude_client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}]
        )
        text = response.content[0].text.strip()
        # JSON clean karo
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()

        result = json.loads(text)
        logger.info(f"🤖 Claude Analysis: {result}")
        return result

    except Exception as e:
        logger.error(f"Claude error: {e}")
        return {
            "approved": False,
            "confidence": 0,
            "signal_quality": "WEAK",
            "key_reason": f"Claude unavailable: {str(e)}",
            "red_flags": ["AI analysis failed"],
            "risk_assessment": "EXTREME"
        }

# ================================================================
# TRADE EXECUTOR
# ================================================================
def execute_trade(signal, position_plan, account):
    """Broker pe trade execute karo"""
    action = signal["action"].lower()
    symbol = signal["symbol"].replace("BINANCE:", "").replace("NASDAQ:", "").replace("NYSE:", "")
    qty = position_plan["qty"]
    stop_loss = position_plan["stop_loss"]
    take_profit = position_plan["take_profit"]

    # Existing position close karo agar opposite hai
    try:
        existing = alpaca.get_position(symbol)
        if existing:
            existing_side = existing.side
            if (action == "buy" and existing_side == "short") or \
               (action == "sell" and existing_side == "long"):
                alpaca.close_position(symbol)
                logger.info(f"♻️ Opposite position closed for {symbol}")
                time.sleep(1)
    except Exception:
        pass

    # Order submit karo
    side = "buy" if action == "buy" else "sell"

    try:
        order = alpaca.submit_order(
            symbol=symbol,
            qty=qty,
            side=side,
            type='market',
            time_in_force='day',
            order_class='bracket',
            stop_loss={'stop_price': str(stop_loss)},
            take_profit={'limit_price': str(take_profit)}
        )

        result = {
            "order_id": order.id,
            "symbol": symbol,
            "action": action,
            "qty": qty,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "status": order.status,
            "timestamp": datetime.now().isoformat(),
            "mode": "PAPER" if PAPER else "LIVE 💸"
        }

        # History mein save karo
        trade_history.append({**result, "signal": signal})
        daily_stats["trades"] += 1

        return result

    except Exception as e:
        logger.error(f"Order failed: {e}")
        raise

# ================================================================
# MAIN WEBHOOK ENDPOINT
# ================================================================
@app.post("/webhook")
async def tradingview_webhook(
    request: Request,
    x_webhook_secret: str = Header(None)
):
    """
    TradingView yahan signal bhejta hai.
    URL: https://your-app.onrender.com/webhook
    Header: x-webhook-secret: your_password
    """

    # Security
    if x_webhook_secret != WEBHOOK_SECRET:
        logger.warning("⛔ Unauthorized attempt!")
        raise HTTPException(status_code=401, detail="Unauthorized")

    # Parse signal
    try:
        body = await request.body()
        signal = json.loads(body.decode('utf-8'))
        logger.info(f"\n{'='*50}")
        logger.info(f"📨 SIGNAL RECEIVED: {signal}")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Bad JSON: {e}")

    # Validate
    for field in ["action", "symbol", "price"]:
        if field not in signal:
            raise HTTPException(status_code=400, detail=f"Missing: {field}")

    price = float(signal.get("price", 0))
    if price <= 0:
        raise HTTPException(status_code=400, detail="Invalid price")

    # STEP 1: Account check
    account = risk_manager.get_account()
    if not account:
        return JSONResponse({"status": "error", "message": "Account unavailable"})

    logger.info(f"💰 Equity: ${account['equity']:.2f} | Daily P&L: ${account['daily_pnl']:.2f}")

    # STEP 2: Risk checks
    risk_blocks = risk_manager.check_all_risks(account)
    if risk_blocks:
        logger.warning(f"🛑 RISK BLOCKED: {risk_blocks}")
        return JSONResponse({
            "status": "blocked",
            "reasons": risk_blocks
        })

    # STEP 3: Position plan
    position_plan = risk_manager.calculate_position(account, price, signal["action"])
    logger.info(f"📊 Plan: qty={position_plan['qty']} | SL=${position_plan['stop_loss']} | TP=${position_plan['take_profit']}")
    logger.info(f"   Risk: ${position_plan['risk_amount']:.2f} | Potential: ${position_plan['potential_profit']:.2f}")

    # STEP 4: Claude AI Analysis
    logger.info("🤖 Claude analyzing...")
    ai = claude_deep_analysis(signal, account, position_plan)

    if not ai.get("approved"):
        logger.info(f"❌ Claude REJECTED: {ai.get('key_reason')}")
        return JSONResponse({
            "status": "rejected",
            "ai_reason": ai.get("key_reason"),
            "confidence": ai.get("confidence"),
            "red_flags": ai.get("red_flags", [])
        })

    if ai.get("confidence", 0) < RISK_CONFIG["min_ai_confidence"]:
        logger.info(f"⚠️ Low confidence: {ai.get('confidence')}%")
        return JSONResponse({
            "status": "low_confidence",
            "confidence": ai.get("confidence"),
            "required": RISK_CONFIG["min_ai_confidence"]
        })

    logger.info(f"✅ Claude APPROVED: {ai.get('confidence')}% | {ai.get('key_reason')}")

    # STEP 5: Execute!
    try:
        result = execute_trade(signal, position_plan, account)
        logger.info(f"🚀 TRADE EXECUTED: {result}")
        logger.info(f"{'='*50}\n")

        return JSONResponse({
            "status": "success ✅",
            "trade": result,
            "ai_analysis": {
                "confidence": ai.get("confidence"),
                "signal_quality": ai.get("signal_quality"),
                "reason": ai.get("key_reason"),
                "risk_level": ai.get("risk_assessment")
            },
            "account_after": {
                "equity": account["equity"],
                "daily_pnl": account["daily_pnl"]
            }
        })

    except Exception as e:
        logger.error(f"❌ Execution failed: {e}")
        return JSONResponse({"status": "error", "message": str(e)})


# ================================================================
# MONITORING ENDPOINTS
# ================================================================
@app.get("/")
def dashboard():
    account = risk_manager.get_account()
    return {
        "bot": "Super Aggressive Pro Max Bot 🔥",
        "mode": "📝 PAPER TRADING" if PAPER else "💸 LIVE TRADING",
        "status": "Running ✅",
        "equity": f"${account['equity']:.2f}" if account else "N/A",
        "daily_pnl": f"${account['daily_pnl']:.2f}" if account else "N/A",
        "open_positions": account["open_positions"] if account else 0,
        "total_trades_today": daily_stats["trades"],
        "ai_min_confidence": f"{RISK_CONFIG['min_ai_confidence']}%",
        "risk_per_trade": f"{RISK_CONFIG['risk_per_trade_pct']*100}%",
        "leverage": f"{RISK_CONFIG['max_leverage']}x"
    }

@app.get("/positions")
def get_positions():
    try:
        positions = alpaca.list_positions()
        return [{
            "symbol": p.symbol,
            "side": p.side,
            "qty": p.qty,
            "entry_price": p.avg_entry_price,
            "current_price": p.current_price,
            "unrealized_pnl": p.unrealized_pl,
            "unrealized_pnl_pct": f"{float(p.unrealized_plpc)*100:.2f}%"
        } for p in positions]
    except Exception as e:
        return {"error": str(e)}

@app.get("/history")
def get_history():
    return {
        "total_trades": len(trade_history),
        "today_stats": daily_stats,
        "recent_trades": trade_history[-10:]
    }

@app.get("/account")
def get_account():
    return risk_manager.get_account()

@app.delete("/emergency-stop")
def emergency_stop():
    """🚨 EMERGENCY: Saari positions FORAN band karo"""
    try:
        alpaca.cancel_all_orders()
        alpaca.close_all_positions()
        logger.warning("🚨 EMERGENCY STOP EXECUTED!")
        return {"status": "✅ ALL POSITIONS CLOSED!", "time": datetime.now().isoformat()}
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    import uvicorn
    logger.info("🔥 Super Aggressive Pro Max Bot Starting...")
    logger.info(f"Mode: {'PAPER TRADING 📝' if PAPER else 'LIVE TRADING 💸'}")
    uvicorn.run(app, host="0.0.0.0", port=8000)
