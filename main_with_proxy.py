import os
import time
import requests
import logging
from binance.client import Client
from binance.exceptions import BinanceAPIException

# Logging o'rnatish
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Kalitlar
API_KEY = os.environ.get('BINANCE_API_KEY')
API_SECRET = os.environ.get('BINANCE_API_SECRET')
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
CHAT_ID = os.environ.get('CHAT_ID')
PROXY_URL = os.environ.get('PROXY_URL', '')  # Ixtiyoriy proxy

# Kalitlar bo'shmi yoki yo'qmi tekshirish
if not all([API_KEY, API_SECRET, TELEGRAM_TOKEN, CHAT_ID]):
    logger.error("❌ Environment variables to'liq emas!")
    logger.error(f"API_KEY: {bool(API_KEY)}")
    logger.error(f"API_SECRET: {bool(API_SECRET)}")
    logger.error(f"TELEGRAM_TOKEN: {bool(TELEGRAM_TOKEN)}")
    logger.error(f"CHAT_ID: {bool(CHAT_ID)}")
    exit(1)

# Binance client'ni yaratish (proxy bilan)
try:
    requests_params = {"timeout": 30}
    
    # Agar proxy bo'lsa qo'shish
    if PROXY_URL:
        proxies = {
            "http": PROXY_URL,
            "https": PROXY_URL,
        }
        requests_params["proxies"] = proxies
        logger.info(f"🌐 Proxy ishlatilmoqda: {PROXY_URL[:30]}...")
    
    client = Client(API_KEY, API_SECRET, requests_params=requests_params)
    logger.info("✅ Binance client ulanish muvaffaqiyatli")
except BinanceAPIException as e:
    logger.error(f"❌ Binance API xatosi: {e}")
    exit(1)
except Exception as e:
    logger.error(f"❌ Boshqa xato: {e}")
    exit(1)

def send_telegram(msg):
    """Telegram'ga xabar yuborish"""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        response = requests.post(
            url, 
            data={"chat_id": CHAT_ID, "text": msg},
            timeout=10
        )
        if response.status_code == 200:
            logger.info("✅ Telegram xabari yuborildi")
        else:
            logger.error(f"❌ Telegram xatosi: {response.text}")
    except Exception as e:
        logger.error(f"❌ Telegram yuborish xatosi: {e}")

def check_signal():
    """BTC signal'ini tekshirish"""
    try:
        # BTC narxini olish
        price = client.get_symbol_ticker(symbol="BTCUSDT")
        btc_price = float(price['price'])
        
        # RSI hisoblash uchun ma'lumot (14 soatlik)
        klines = client.get_klines(symbol="BTCUSDT", interval="1h", limit=14)
        closes = [float(k[4]) for k in klines]
        
        msg = f"📊 BTC narxi: ${btc_price:,.2f}\n"
        msg += f"⏰ Vaqt: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        
        if btc_price < closes[-2]:
            msg += "🔴 Signal: SOTISH (narx tushyapti)"
            logger.info("🔴 SOTISH signali")
        else:
            msg += "🟢 Signal: SOTIB OLISH (narx o'syapti)"
            logger.info("🟢 SOTIB OLISH signali")
        
        send_telegram(msg)
        
    except BinanceAPIException as e:
        error_msg = f"❌ Binance API xatosi: {e}"
        logger.error(error_msg)
        send_telegram(error_msg)
    except Exception as e:
        error_msg = f"❌ Xato yuz berdi: {str(e)}"
        logger.error(error_msg)
        send_telegram(error_msg)

# Bot'ni ishga tushirish
if __name__ == "__main__":
    logger.info("🚀 Trading bot ishga tushdi...")
    send_telegram("🚀 Trading bot ishga tushdi! (Binance + Proxy)")
    
    while True:
        try:
            check_signal()
            logger.info("⏳ 1 soatdan keyin yana tekshiradi...")
            time.sleep(3600)  # Har 1 soatda
        except KeyboardInterrupt:
            logger.info("🛑 Bot to'xtatildi")
            break
        except Exception as e:
            logger.error(f"❌ Loopda xato: {e}")
            time.sleep(60)  # Xato bo'lsa 1 minutdan keyin qayta urini
