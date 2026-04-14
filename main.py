import os
import time
import requests
from binance.client import Client

# Kalitlar
API_KEY = os.environ.get('BINANCE_API_KEY')
API_SECRET = os.environ.get('BINANCE_SECRET_KEY')
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
CHAT_ID = os.environ.get('CHAT_ID')

client = Client(API_KEY, API_SECRET)

def send_telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": CHAT_ID, "text": msg})

def check_signal():
    # BTC narxini olish
    price = client.get_symbol_ticker(symbol="BTCUSDT")
    btc_price = float(price['price'])
    
    # RSI hisoblash uchun ma'lumot
    klines = client.get_klines(symbol="BTCUSDT", interval="1h", limit=14)
    closes = [float(k[4]) for k in klines]
    
    msg = f"📊 BTC narxi: ${btc_price:,.2f}\n"
    
    if btc_price < closes[-2]:
        msg += "🔴 Signal: SOTISH (narx tushyapti)"
    else:
        msg += "🟢 Signal: SOTIB OLISH (narx o'syapti)"
    
    send_telegram(msg)

while True:
    check_signal()
    time.sleep(3600)  # Har 1 soatda
