import os
import time
import json
import logging
import requests
from datetime import datetime
from binance.client import Client
from binance.exceptions import BinanceAPIException

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Environment variables
API_KEY = os.environ.get('BINANCE_API_KEY')
API_SECRET = os.environ.get('BINANCE_API_SECRET')
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
CHAT_ID = os.environ.get('CHAT_ID')
CLAUDE_API_KEY = os.environ.get('CLAUDE_API_KEY')

# Trading settings
SYMBOL = "BTCUSDT"
TRADE_AMOUNT = 0.001  # BTC miqdori
MAX_RISK = 50  # USDT risk limit

# Kalitlar tekshirish
if not all([API_KEY, API_SECRET, TELEGRAM_TOKEN, CHAT_ID, CLAUDE_API_KEY]):
    logger.error("❌ Environment variables to'liq emas!")
    exit(1)

# Binance client
try:
    client = Client(API_KEY, API_SECRET)
    logger.info("✅ Binance API ulanish muvaffaqiyatli")
except Exception as e:
    logger.error(f"❌ Binance xatosi: {e}")
    exit(1)

# Trading history (database o'rniga)
TRADES = []

def send_telegram(msg):
    """Telegram'ga xabar yuborish"""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": CHAT_ID, "text": msg}, timeout=10)
    except Exception as e:
        logger.error(f"❌ Telegram xatosi: {e}")

def get_market_data():
    """Market ma'lumotlarini olish"""
    try:
        # BTC/USDT ma'lumotlari
        price = client.get_symbol_ticker(symbol=SYMBOL)
        current_price = float(price['price'])
        
        # 1 soatlik klines (Smart Money analizi uchun)
        klines = client.get_klines(symbol=SYMBOL, interval="1h", limit=24)
        
        closes = [float(k[4]) for k in klines]
        highs = [float(k[2]) for k in klines]
        lows = [float(k[3]) for k in klines]
        volumes = [float(k[7]) for k in klines]
        
        # Smart Money indikatorlari
        highest_high = max(highs[-4:])  # Oxirgi 4 soatning eng yuqori
        lowest_low = min(lows[-4:])     # Oxirgi 4 soatning eng past
        avg_volume = sum(volumes[-4:]) / 4
        
        data = {
            "current_price": current_price,
            "highest_high_4h": highest_high,
            "lowest_low_4h": lowest_low,
            "avg_volume_4h": avg_volume,
            "closes_24h": closes,
            "current_volume": volumes[-1],
            "price_change_4h": ((closes[-1] - closes[-4]) / closes[-4]) * 100 if closes[-4] != 0 else 0
        }
        
        return data
    except Exception as e:
        logger.error(f"❌ Market data xatosi: {e}")
        return None

def analyze_with_claude(market_data):
    """Claude AI'ga smart money analizi qildiramiz"""
    try:
        prompt = f"""
        Sen professional Smart Money trading analystisin. Quyidagi market data'ni analiz qil va 
        SHORT (qisqa) savdo signali ber.
        
        Market Data:
        - Current Price: ${market_data['current_price']:,.2f}
        - Highest High (4h): ${market_data['highest_high_4h']:,.2f}
        - Lowest Low (4h): ${market_data['lowest_low_4h']:,.2f}
        - Price Change (4h): {market_data['price_change_4h']:.2f}%
        - Current Volume: {market_data['current_volume']:,.0f}
        - Avg Volume (4h): {market_data['avg_volume_4h']:,.0f}
        
        Smart Money Concept yuzasidan quyidagilarni analiz qil:
        1. Liquidity Level'lari
        2. Volume Profile
        3. Price Action (Supply/Demand zonal)
        4. Order Flow
        5. Market Structure
        
        Javobda FAQAT JSON format'da ber (Uzbek tilida):
        {{
            "action": "BUY" yoki "SELL" yoki "HOLD",
            "confidence": 0-100,
            "reason": "Qisqa sabab (Uzbek tilida)",
            "entry_price": float,
            "stop_loss": float,
            "take_profit": float,
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
            
            # JSON'ni extract qil
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

def execute_short_trade(analysis, market_data):
    """Short savdo qilish"""
    try:
        if analysis['action'] != 'SELL':
            return
        
        logger.info(f"🔴 SHORT SAVDO signali! Confidence: {analysis['confidence']}%")
        
        # Entry price
        entry_price = market_data['current_price']
        stop_loss = analysis['stop_loss']
        take_profit = analysis['take_profit']
        
        # Risk hisoblash
        risk = (entry_price - stop_loss) * TRADE_AMOUNT
        
        if risk > MAX_RISK:
            logger.warning(f"⚠️ Risk juda yuqori: ${risk:.2f} > ${MAX_RISK}")
            return
        
        # Savdoni qayd qilish
        trade = {
            "timestamp": datetime.now().isoformat(),
            "type": "SHORT",
            "entry_price": entry_price,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "amount": TRADE_AMOUNT,
            "risk": risk,
            "confidence": analysis['confidence'],
            "reason": analysis['reason'],
            "status": "OPEN"
        }
        
        TRADES.append(trade)
        
        # Telegram xabar
        msg = f"""
🔴 SHORT SAVDO OCHILDI!
━━━━━━━━━━━━━━━━━━
📊 Entry: ${entry_price:,.2f}
🎯 Take Profit: ${take_profit:,.2f}
🛑 Stop Loss: ${stop_loss:,.2f}
📈 Risk/Reward: {analysis['risk_reward_ratio']:.2f}
💪 Confidence: {analysis['confidence']}%
━━━━━━━━━━━━━━━━━━
💡 Sabab: {analysis['reason']}
🕐 Vaqt: {trade['timestamp']}
        """
        
        send_telegram(msg)
        logger.info(f"✅ SHORT savdo qayd qilindi: {trade}")
        
    except Exception as e:
        logger.error(f"❌ Trade execution xatosi: {e}")

def check_trade_levels():
    """Ochiq savdolarning levels'ni tekshirish"""
    try:
        current_price = client.get_symbol_ticker(symbol=SYMBOL)
        current_price = float(current_price['price'])
        
        for trade in TRADES:
            if trade['status'] != 'OPEN':
                continue
            
            # Take profit tekshirish
            if trade['type'] == 'SHORT' and current_price <= trade['take_profit']:
                trade['status'] = 'CLOSED_TP'
                profit = (trade['entry_price'] - current_price) * TRADE_AMOUNT
                
                msg = f"""
✅ SHORT SAVDO YOPILDI (TAKE PROFIT)!
━━━━━━━━━━━━━━━━━━
Entry: ${trade['entry_price']:,.2f}
Exit: ${current_price:,.2f}
Profit: ${profit:,.2f}
━━━━━━━━━━━━━━━━━━
🕐 {datetime.now().isoformat()}
                """
                send_telegram(msg)
                logger.info(msg)
            
            # Stop loss tekshirish
            elif trade['type'] == 'SHORT' and current_price >= trade['stop_loss']:
                trade['status'] = 'CLOSED_SL'
                loss = (current_price - trade['entry_price']) * TRADE_AMOUNT
                
                msg = f"""
❌ SHORT SAVDO YOPILDI (STOP LOSS)!
━━━━━━━━━━━━━━━━━━
Entry: ${trade['entry_price']:,.2f}
Exit: ${current_price:,.2f}
Loss: -${loss:,.2f}
━━━━━━━━━━━━━━━━━━
🕐 {datetime.now().isoformat()}
                """
                send_telegram(msg)
                logger.error(msg)
    
    except Exception as e:
        logger.error(f"❌ Level check xatosi: {e}")

def trading_loop():
    """Asosiy AI trading loop"""
    logger.info("🚀 Smart Money AI Agent ishga tushdi!")
    send_telegram("🚀 Smart Money AI Trading Agent ishga tushdi!\n\n💡 Claude AI har 5 minutda market'ni analiz qiladi...")
    
    while True:
        try:
            # Market ma'lumotlarini olish
            market_data = get_market_data()
            if not market_data:
                time.sleep(60)
                continue
            
            # Claude'ga analiz qildiramiz
            analysis = analyze_with_claude(market_data)
            
            if analysis:
                logger.info(f"📊 Claude Analysis: {analysis}")
                
                # Short savdo signali bo'lsa execute qil
                if analysis['action'] == 'SELL' and analysis['confidence'] >= 60:
                    execute_short_trade(analysis, market_data)
            
            # Ochiq savdolarni tekshirish
            check_trade_levels()
            
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
