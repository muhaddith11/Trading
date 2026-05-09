import os
import time
import logging
from binance.client import Client
from binance.exceptions import BinanceAPIException, BinanceOrderException
import requests

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Kalitlar
API_KEY = os.environ.get('BINANCE_API_KEY')
API_SECRET = os.environ.get('BINANCE_API_SECRET')
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
CHAT_ID = os.environ.get('CHAT_ID')

# TRADING SOZLAMALARI
SYMBOL = "BTCUSDT"  # Trading juftligi
TRADE_AMOUNT = 0.001  # BTC miqdori (KICHIK!)
RSI_BUY_LEVEL = 30  # RSI <= 30 bo'lsa SOTIB OL
RSI_SELL_LEVEL = 70  # RSI >= 70 bo'lsa SOT

# Kalitlar tekshirish
if not all([API_KEY, API_SECRET, TELEGRAM_TOKEN, CHAT_ID]):
    logger.error("❌ Environment variables to'liq emas!")
    exit(1)

# Binance client
try:
    client = Client(API_KEY, API_SECRET, requests_params={"timeout": 30})
    logger.info("✅ Binance API ulanish muvaffaqiyatli")
except Exception as e:
    logger.error(f"❌ Binance xatosi: {e}")
    exit(1)

def send_telegram(msg):
    """Telegram'ga xabar yuborish"""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": CHAT_ID, "text": msg}, timeout=10)
        logger.info("✅ Telegram xabari yuborildi")
    except Exception as e:
        logger.error(f"❌ Telegram xatosi: {e}")

def calculate_rsi(prices, period=14):
    """RSI hisoblash"""
    if len(prices) < period:
        return None
    
    deltas = [prices[i] - prices[i-1] for i in range(1, len(prices))]
    seed = deltas[:period]
    
    up = sum([x for x in seed if x > 0]) / period
    down = -sum([x for x in seed if x < 0]) / period
    
    rs = up / down if down != 0 else 0
    rsi = 100 - (100 / (1 + rs))
    
    for i in range(period, len(deltas)):
        delta = deltas[i]
        up = (up * 13 + (delta if delta > 0 else 0)) / 14
        down = (down * 13 + (-delta if delta < 0 else 0)) / 14
        
        rs = up / down if down != 0 else 0
        rsi = 100 - (100 / (1 + rs))
    
    return rsi

def get_price_and_rsi():
    """Narx va RSI'ni olish"""
    try:
        # Oxirgi 14 soatning ma'lumotini olish
        klines = client.get_klines(symbol=SYMBOL, interval="1h", limit=14)
        closes = [float(k[4]) for k in klines]
        
        current_price = closes[-1]
        rsi = calculate_rsi(closes)
        
        return current_price, rsi
    except Exception as e:
        logger.error(f"❌ Ma'lumot olish xatosi: {e}")
        return None, None

def get_balance(asset):
    """Balansni tekshirish"""
    try:
        balance = client.get_asset_balance(asset)
        return float(balance['free'])
    except Exception as e:
        logger.error(f"❌ Balance xatosi: {e}")
        return 0

def place_buy_order():
    """SOTIB OLISH buyrug'i"""
    try:
        logger.info("🟢 SOTIB OLISH signali - Buyrug'i jonatilmoqda...")
        
        order = client.order_market_buy(
            symbol=SYMBOL,
            quantity=TRADE_AMOUNT
        )
        
        msg = f"🟢 SOTIB OLISH MUVAFFAQ!\n"
        msg += f"Summa: {TRADE_AMOUNT} BTC\n"
        msg += f"Order ID: {order['orderId']}"
        
        send_telegram(msg)
        logger.info(f"✅ SOTIB OLINDI: {order}")
        return True
    except BinanceOrderException as e:
        msg = f"❌ SOTIB OLISH XATOSI: {e}"
        send_telegram(msg)
        logger.error(msg)
        return False
    except Exception as e:
        msg = f"❌ XATO: {e}"
        send_telegram(msg)
        logger.error(msg)
        return False

def place_sell_order():
    """SOTISH buyrug'i"""
    try:
        # BTC miqdorini tekshirish
        btc_balance = get_balance("BTC")
        
        if btc_balance < TRADE_AMOUNT:
            msg = f"⚠️ BTC yetarli emas! Balans: {btc_balance}"
            send_telegram(msg)
            logger.warning(msg)
            return False
        
        logger.info("🔴 SOTISH signali - Buyrug'i jonatilmoqda...")
        
        order = client.order_market_sell(
            symbol=SYMBOL,
            quantity=TRADE_AMOUNT
        )
        
        msg = f"🔴 SOTISH MUVAFFAQ!\n"
        msg += f"Summa: {TRADE_AMOUNT} BTC\n"
        msg += f"Order ID: {order['orderId']}"
        
        send_telegram(msg)
        logger.info(f"✅ SOTILDI: {order}")
        return True
    except BinanceOrderException as e:
        msg = f"❌ SOTISH XATOSI: {e}"
        send_telegram(msg)
        logger.error(msg)
        return False
    except Exception as e:
        msg = f"❌ XATO: {e}"
        send_telegram(msg)
        logger.error(msg)
        return False

def trading_loop():
    """Asosiy trading loop"""
    logger.info("🚀 Trading bot ishga tushdi!")
    send_telegram("🚀 Automated Trading Bot ishga tushdi!")
    send_telegram(f"⚙️ Settings:\nSymbol: {SYMBOL}\nAmount: {TRADE_AMOUNT} BTC\nRSI Buy: {RSI_BUY_LEVEL}\nRSI Sell: {RSI_SELL_LEVEL}")
    
    last_action = None  # Oxirgi harakatni rememberlash
    
    while True:
        try:
            price, rsi = get_price_and_rsi()
            
            if price is None or rsi is None:
                logger.warning("⚠️ Ma'lumotni olib bo'lmadi")
                time.sleep(60)
                continue
            
            msg = f"📊 BTC Narxi: ${price:,.2f}\n"
            msg += f"📈 RSI: {rsi:.2f}\n"
            msg += f"⏰ {time.strftime('%H:%M:%S')}"
            
            logger.info(msg)
            
            # SOTIB OLISH SIGNALI
            if rsi <= RSI_BUY_LEVEL and last_action != "BUY":
                logger.warning(f"⚠️ RSI={rsi:.2f} <= {RSI_BUY_LEVEL} - SOTIB OLISH!")
                if place_buy_order():
                    last_action = "BUY"
            
            # SOTISH SIGNALI
            elif rsi >= RSI_SELL_LEVEL and last_action == "BUY":
                logger.warning(f"⚠️ RSI={rsi:.2f} >= {RSI_SELL_LEVEL} - SOTISH!")
                if place_sell_order():
                    last_action = "SELL"
            
            # Har 5 minutda tekshirish
            time.sleep(300)
        
        except Exception as e:
            logger.error(f"❌ Loopda xato: {e}")
            time.sleep(60)

# Ishga tushirish
if __name__ == "__main__":
    trading_loop()
