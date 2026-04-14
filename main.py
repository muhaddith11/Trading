import os
import time
import json
import logging
import requests
from datetime import datetime
from decimal import Decimal
from binance.client import Client
from binance.exceptions import BinanceAPIException

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Environment variables
API_KEY = os.environ.get('BINANCE_API_KEY')
API_SECRET = os.environ.get('BINANCE_API_SECRET')
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
CHAT_ID = os.environ.get('CHAT_ID')
CLAUDE_API_KEY = os.environ.get('CLAUDE_API_KEY')

# Trading settings - FUTURES
SYMBOL = "BTCUSDT"
TOTAL_BALANCE = 1000  # USDT (taqqoslash uchun)
POSITION_SIZE = TOTAL_BALANCE / 4  # 1/4 = 250 USDT
LEVERAGE = 4  # 4x leverage
MAX_LEVERAGE = 4

# Risk management
STOP_LOSS_PERCENT = 2  # 2% stop loss
TAKE_PROFIT_PERCENT = 6  # 6% take profit

# Validation
if not all([API_KEY, API_SECRET, TELEGRAM_TOKEN, CHAT_ID, CLAUDE_API_KEY]):
    logger.error("❌ Environment variables to'liq emas!")
    exit(1)

# Binance Futures client
try:
    client = Client(API_KEY, API_SECRET)
    logger.info("✅ Binance Futures API ulanish muvaffaqiyatli")
except Exception as e:
    logger.error(f"❌ Binance xatosi: {e}")
    exit(1)

# Trading history (In-memory database)
TRADES = []
ACCOUNT_BALANCE = TOTAL_BALANCE
ACTIVE_POSITION = None

def send_telegram(msg):
    """Telegram'ga xabar yuborish"""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(
            url,
            data={"chat_id": CHAT_ID, "text": msg},
            timeout=10
        )
        logger.info("✅ Telegram xabari yuborildi")
    except Exception as e:
        logger.error(f"❌ Telegram xatosi: {e}")

def get_futures_market_data():
    """Futures market ma'lumotlarini olish"""
    try:
        # Current price
        ticker = client.futures_symbol_ticker(symbol=SYMBOL)
        current_price = float(ticker['price'])
        
        # 4 soatlik ma'lumot (Smart Money analizi uchun)
        klines = client.futures_klines(
            symbol=SYMBOL,
            interval='1h',
            limit=24
        )
        
        closes = [float(k[4]) for k in klines]
        highs = [float(k[2]) for k in klines]
        lows = [float(k[3]) for k in klines]
        volumes = [float(k[7]) for k in klines]
        
        # Smart Money indikatorlari
        highest_high_4h = max(highs[-4:])
        lowest_low_4h = min(lows[-4:])
        avg_volume_4h = sum(volumes[-4:]) / 4
        volume_spike = volumes[-1] / avg_volume_4h if avg_volume_4h > 0 else 1
        
        data = {
            "current_price": current_price,
            "highest_high_4h": highest_high_4h,
            "lowest_low_4h": lowest_low_4h,
            "avg_volume_4h": avg_volume_4h,
            "volume_spike": volume_spike,
            "closes_24h": closes,
            "current_volume": volumes[-1],
            "price_change_4h": ((closes[-1] - closes[-4]) / closes[-4]) * 100 if closes[-4] != 0 else 0,
            "rsi": calculate_rsi(closes)
        }
        
        return data
    except Exception as e:
        logger.error(f"❌ Market data xatosi: {e}")
        return None

def calculate_rsi(prices, period=14):
    """RSI hisoblash"""
    if len(prices) < period:
        return 50
    
    deltas = [prices[i] - prices[i-1] for i in range(1, len(prices))]
    seed = deltas[:period]
    
    up = sum([x for x in seed if x > 0]) / period
    down = -sum([x for x in seed if x < 0]) / period
    
    if down == 0:
        return 100
    
    rs = up / down
    rsi = 100 - (100 / (1 + rs))
    
    for i in range(period, len(deltas)):
        delta = deltas[i]
        up = (up * 13 + (delta if delta > 0 else 0)) / 14
        down = (down * 13 + (-delta if delta < 0 else 0)) / 14
        
        if down == 0:
            rsi = 100
        else:
            rs = up / down
            rsi = 100 - (100 / (1 + rs))
    
    return rsi

def analyze_with_claude(market_data):
    """Claude AI smart money analizi"""
    try:
        prompt = f"""
        Sen professional Smart Money Futures trader. Binance Futures'da SHORT savdo signali berish uchun quyidagi ma'lumotni analiz qil.
        
        MUHIM: FAQAT SHORT TRADES QABUL QIL (4x leverage, futures)!
        
        Market Data:
        - Current Price: ${market_data['current_price']:,.2f}
        - Highest High (4h): ${market_data['highest_high_4h']:,.2f}
        - Lowest Low (4h): ${market_data['lowest_low_4h']:,.2f}
        - Price Change (4h): {market_data['price_change_4h']:.2f}%
        - RSI: {market_data['rsi']:.2f}
        - Volume Spike: {market_data['volume_spike']:.2f}x
        
        Smart Money Strategy'siga ko'ra analiz qil:
        1. Liquidity level'lari
        2. Supply/Demand zone'lari
        3. Order flow analysis
        4. Market structure (Higher High/Lower Low)
        5. Volume profile
        
        Position size: 250 USDT (4x leverage = 1000 USDT exposure)
        Stop Loss: 2%
        Take Profit: 6%
        
        Javobda FAQAT JSON format'da ber (O'zbek tilida):
        {{
            "action": "SHORT" yoki "HOLD",
            "confidence": 0-100,
            "reason": "Qisqa sabab (O'zbek)",
            "entry_price": {market_data['current_price']},
            "stop_loss": kalkulyatsiya qiling,
            "take_profit": kalkulyatsiya qiling,
            "risk_reward_ratio": float
        }}
        
        MUHIM: Faqat JSON, boshqa hech narsa yozmang!
        """
        
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": CLAUDE_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-opus-4-1-20250805",
                "max_tokens": 500,
                "messages": [
                    {"role": "user", "content": prompt}
                ]
            },
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            text = result['content'][0]['text']
            
            # JSON extract
            json_start = text.find('{')
            json_end = text.rfind('}') + 1
            
            if json_start != -1 and json_end > json_start:
                json_str = text[json_start:json_end]
                analysis = json.loads(json_str)
                return analysis
        
        logger.error(f"❌ Claude API xatosi: {response.text}")
        return None
        
    except Exception as e:
        logger.error(f"❌ Claude analiz xatosi: {e}")
        return None

def open_short_position(analysis, market_data):
    """Short position oching (Futures)"""
    global ACTIVE_POSITION, ACCOUNT_BALANCE
    
    try:
        if ACTIVE_POSITION is not None:
            logger.warning("⚠️ Allaqachon ochiq position bor!")
            return False
        
        if analysis['action'] != 'SHORT':
            return False
        
        entry_price = float(analysis['entry_price'])
        stop_loss = float(analysis['stop_loss'])
        take_profit = float(analysis['take_profit'])
        
        # Quantity hisoblash (4x leverage)
        quantity = round(POSITION_SIZE * LEVERAGE / entry_price, 3)
        
        # Risk hisoblash
        risk_per_trade = POSITION_SIZE * (STOP_LOSS_PERCENT / 100)
        
        logger.info(f"🔴 SHORT POSITION OCHILDI!")
        logger.info(f"Entry: ${entry_price:,.2f}")
        logger.info(f"Stop Loss: ${stop_loss:,.2f}")
        logger.info(f"Take Profit: ${take_profit:,.2f}")
        logger.info(f"Quantity: {quantity} BTC")
        logger.info(f"Leverage: {LEVERAGE}x")
        logger.info(f"Risk: ${risk_per_trade:,.2f}")
        
        # Position'ni qayd qilish (real Binance API calls yo'q test uchun)
        position = {
            "timestamp": datetime.now().isoformat(),
            "type": "SHORT",
            "status": "OPEN",
            "entry_price": entry_price,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "quantity": quantity,
            "position_size": POSITION_SIZE,
            "leverage": LEVERAGE,
            "confidence": analysis['confidence'],
            "reason": analysis['reason'],
            "risk_amount": risk_per_trade,
            "risk_reward": analysis['risk_reward_ratio'],
            "pnl": 0,
            "pnl_percent": 0
        }
        
        ACTIVE_POSITION = position
        TRADES.append(position)
        
        # Telegram xabar
        msg = f"""
🔴 SHORT POSITION OCHILDI!
{'═' * 40}
📊 Entry: ${entry_price:,.2f}
🎯 Take Profit: ${take_profit:,.2f}
🛑 Stop Loss: ${stop_loss:,.2f}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💰 Position Size: ${POSITION_SIZE:,.2f}
📈 Leverage: {LEVERAGE}x
💸 Risk: ${risk_per_trade:,.2f}
📊 Quantity: {quantity} BTC
🎲 Risk/Reward: {analysis['risk_reward_ratio']:.2f}
💪 Confidence: {analysis['confidence']}%
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💡 Sabab: {analysis['reason']}
🕐 {position['timestamp']}
        """
        
        send_telegram(msg)
        return True
        
    except Exception as e:
        logger.error(f"❌ Position open xatosi: {e}")
        send_telegram(f"❌ Position open xatosi: {e}")
        return False

def monitor_position(current_price):
    """Ochiq position'ni kuzatish"""
    global ACTIVE_POSITION, ACCOUNT_BALANCE
    
    if ACTIVE_POSITION is None or ACTIVE_POSITION['status'] != 'OPEN':
        return
    
    try:
        entry = ACTIVE_POSITION['entry_price']
        stop_loss = ACTIVE_POSITION['stop_loss']
        take_profit = ACTIVE_POSITION['take_profit']
        
        # SHORT trades uchun:
        # Profit: entry - current > 0 (narx pasaysa profit)
        # Loss: current - entry > 0 (narx ko'tarilsa loss)
        
        pnl_points = entry - current_price  # SHORT uchun
        pnl_percent = (pnl_points / entry) * 100
        pnl_amount = pnl_percent * POSITION_SIZE / 100
        
        ACTIVE_POSITION['pnl'] = pnl_amount
        ACTIVE_POSITION['pnl_percent'] = pnl_percent
        
        logger.info(f"📊 Position Monitor: Price ${current_price:,.2f} | PnL: {pnl_percent:+.2f}% (${pnl_amount:+,.2f})")
        
        # TAKE PROFIT tekshirish
        if current_price <= take_profit:
            close_short_position("TAKE_PROFIT", current_price)
        
        # STOP LOSS tekshirish
        elif current_price >= stop_loss:
            close_short_position("STOP_LOSS", current_price)
    
    except Exception as e:
        logger.error(f"❌ Monitor xatosi: {e}")

def close_short_position(reason, current_price):
    """Short position'ni yopish"""
    global ACTIVE_POSITION, ACCOUNT_BALANCE
    
    if ACTIVE_POSITION is None:
        return
    
    try:
        entry = ACTIVE_POSITION['entry_price']
        quantity = ACTIVE_POSITION['quantity']
        risk = ACTIVE_POSITION['risk_amount']
        
        # PnL hisoblash
        pnl_points = entry - current_price
        pnl_percent = (pnl_points / entry) * 100
        pnl_amount = pnl_percent * POSITION_SIZE / 100
        
        # Balance o'zgarishi
        ACCOUNT_BALANCE += pnl_amount
        
        ACTIVE_POSITION['status'] = 'CLOSED'
        ACTIVE_POSITION['close_price'] = current_price
        ACTIVE_POSITION['close_reason'] = reason
        ACTIVE_POSITION['pnl'] = pnl_amount
        ACTIVE_POSITION['pnl_percent'] = pnl_percent
        ACTIVE_POSITION['closed_at'] = datetime.now().isoformat()
        
        # Emoji va rang
        emoji = "✅" if pnl_amount > 0 else "❌"
        color = "🟢" if pnl_amount > 0 else "🔴"
        
        msg = f"""
{emoji} SHORT POSITION YOPILDI!
{'═' * 40}
🎯 Reason: {reason}
Entry: ${entry:,.2f}
Exit: ${current_price:,.2f}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{color} PnL: {pnl_percent:+.2f}% (${pnl_amount:+,.2f})
💰 Account Balance: ${ACCOUNT_BALANCE:,.2f}
📊 ROI: {(pnl_amount / POSITION_SIZE) * 100:+.2f}%
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🕐 {ACTIVE_POSITION['closed_at']}
        """
        
        send_telegram(msg)
        logger.info(msg)
        
        ACTIVE_POSITION = None
    
    except Exception as e:
        logger.error(f"❌ Position close xatosi: {e}")

def print_stats():
    """Trading stats'ni chiqarish"""
    closed_trades = [t for t in TRADES if t['status'] == 'CLOSED']
    
    if not closed_trades:
        return
    
    total_pnl = sum(t['pnl'] for t in closed_trades)
    wins = len([t for t in closed_trades if t['pnl'] > 0])
    losses = len([t for t in closed_trades if t['pnl'] < 0])
    win_rate = (wins / len(closed_trades) * 100) if closed_trades else 0
    
    logger.info(f"""
    ═════════════════════════════════════
    📊 TRADING STATISTICS
    ═════════════════════════════════════
    Total Trades: {len(closed_trades)}
    Wins: {wins} | Losses: {losses}
    Win Rate: {win_rate:.1f}%
    Total PnL: ${total_pnl:,.2f}
    Account Balance: ${ACCOUNT_BALANCE:,.2f}
    ═════════════════════════════════════
    """)

def trading_loop():
    """Asosiy AI trading loop"""
    logger.info("🚀 Smart Money AI Futures Agent ishga tushdi!")
    logger.info(f"💰 Starting Balance: ${ACCOUNT_BALANCE}")
    logger.info(f"📊 Position Size: ${POSITION_SIZE} (4x leverage)")
    
    send_telegram(f"""
🚀 Smart Money AI Futures Agent ishga tushdi!
{'═' * 40}
💰 Starting Balance: ${ACCOUNT_BALANCE}
📊 Position Size: ${POSITION_SIZE}
📈 Leverage: {LEVERAGE}x
🎯 Strategy: SHORT ONLY
⏰ Interval: 5 minutes
🛑 Stop Loss: {STOP_LOSS_PERCENT}%
🎉 Take Profit: {TAKE_PROFIT_PERCENT}%
    """)
    
    while True:
        try:
            # Market ma'lumotlarini olish
            market_data = get_futures_market_data()
            if not market_data:
                logger.warning("⚠️ Market data olib bo'lmadi")
                time.sleep(60)
                continue
            
            # Ochiq position'ni kuzatish
            monitor_position(market_data['current_price'])
            
            # Claude'ga analiz qildiramiz (faqat ochiq position bo'lmasa)
            if ACTIVE_POSITION is None:
                analysis = analyze_with_claude(market_data)
                
                if analysis and analysis['action'] == 'SHORT':
                    if analysis['confidence'] >= 65:  # 65% confidence threshold
                        logger.info(f"📊 AI Signal: {analysis}")
                        open_short_position(analysis, market_data)
                    else:
                        logger.info(f"⚠️ Confidence juda past: {analysis['confidence']}%")
            
            # Stats
            print_stats()
            
            # 5 minut kutish
            logger.info("⏳ 5 minutdan keyin yana analiz qiladi...")
            time.sleep(300)
        
        except Exception as e:
            logger.error(f"❌ Loop xatosi: {e}")
            send_telegram(f"❌ Bot xatosi: {e}")
            time.sleep(60)

# Ishga tushirish
if __name__ == "__main__":
    trading_loop()
