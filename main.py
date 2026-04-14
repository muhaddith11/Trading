import os
import time
import requests
import logging
from datetime import datetime

# Logging o'rnatish
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Kalitlar
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
CHAT_ID = os.environ.get('CHAT_ID')

# Kalitlar bo'shmi yoki yo'qmi tekshirish
if not all([TELEGRAM_TOKEN, CHAT_ID]):
    logger.error("❌ Environment variables to'liq emas!")
    logger.error(f"TELEGRAM_TOKEN: {bool(TELEGRAM_TOKEN)}")
    logger.error(f"CHAT_ID: {bool(CHAT_ID)}")
    exit(1)

logger.info("✅ Telegram settings to'g'ri o'rnatildi")

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

def get_btc_price():
    """CoinGecko'dan BTC narxini olish"""
    try:
        url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd&include_market_cap=true&include_24hr_vol=true&include_24hr_change=true"
        response = requests.get(url, timeout=10)
        data = response.json()
        
        btc_data = data['bitcoin']
        price = btc_data['usd']
        change_24h = btc_data['usd_24h_change']
        
        return {
            'price': price,
            'change_24h': change_24h
        }
    except Exception as e:
        logger.error(f"❌ CoinGecko xatosi: {e}")
        return None

def check_signal():
    """BTC signal'ini tekshirish"""
    try:
        btc_data = get_btc_price()
        
        if not btc_data:
            send_telegram("❌ BTC narxini olib bo'lmadi!")
            return
        
        btc_price = btc_data['price']
        change_24h = btc_data['change_24h']
        
        msg = f"📊 BTC narxi: ${btc_price:,.2f}\n"
        msg += f"📈 24h o'zgarish: {change_24h:.2f}%\n"
        msg += f"⏰ Vaqt: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        
        if change_24h < 0:
            msg += "🔴 Signal: SOTISH (narx tushyapti)"
            logger.info(f"🔴 SOTISH signali - Narx: ${btc_price:,.2f}")
        else:
            msg += "🟢 Signal: SOTIB OLISH (narx o'syapti)"
            logger.info(f"🟢 SOTIB OLISH signali - Narx: ${btc_price:,.2f}")
        
        send_telegram(msg)
        
    except Exception as e:
        error_msg = f"❌ Xato yuz berdi: {str(e)}"
        logger.error(error_msg)
        send_telegram(error_msg)

# Bot'ni ishga tushirish
if __name__ == "__main__":
    logger.info("🚀 Trading bot ishga tushdi...")
    send_telegram("🚀 Trading bot ishga tushdi! (CoinGecko API)")
    
    while True:
        try:
            check_signal()
            logger.info("⏳ 1 soatdan keyin yana tekshiradi...")
            time.sleep(3600)  # Har 1 soatda
        except KeyboardInterrupt:
            logger.info("🛑 Bot to'xtatildi")
            send_telegram("🛑 Bot to'xtatildi")
            break
        except Exception as e:
            logger.error(f"❌ Loopda xato: {e}")
            time.sleep(60)  # Xato bo'lsa 1 minutdan keyin qayta urini
