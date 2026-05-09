# 🚀 RAILWAY'DA O'RNATISH QOLLANMASI

## 1️⃣ GITHUB'NI YANGILASH

```bash
git clone https://github.com/muhaddith11/Trading.git
cd Trading

# Yangi fayllarni copy qilish
# (main.py, requirements.txt, Procfile)

git add .
git commit -m "Fix: Environment variables va error handling"
git push origin main
```

## 2️⃣ RAILWAY'DA VARIABLES'NI TEKSHIRISH

Railway Dashboard → Variables → Quyidagilarni tekshiring:

```
✅ BINANCE_API_KEY = Nq8PwpdP1acE6H47x3Ifefefufb4hkJ48irkUUJHkaZcw0B4ug40w...
✅ BINANCE_API_SECRET = XOJniGKUQdpSh9uaJ0VTGCF83KJFyR5M55gh1Ap70gks0ImPwmV...
✅ TELEGRAM_TOKEN = 8536471932:AAEA-pZdzimARzx9JrQN_2UL3H2uB22u_DQ
✅ CHAT_ID = 8042807902
```

⚠️ MUHIM: Variable nomi `BINANCE_API_SECRET` bo'lishi kerak, `BINANCE_SECRET_KEY` EMAS!

## 3️⃣ DEPLOYMENT'NI QAYTA ISHGA TUSHIRISH

Railway Dashboard → Deployments → "Redeploy" knopkasini bosing

## 4️⃣ LOGS'NI TEKSHIRISH

Railway → Logs → Quyidagilarni qidiring:

```
✅ "Trading bot ishga tushdi..." - BOT ISHLAYAPTI
❌ "Environment variables to'liq emas" - VARIABLES XATOSI
❌ "Service unavailable from a restricted location" - BINANCE GEOGRAPHY XATOSI
```

## 5️⃣ AGAR HALI XATO BO'LSA

### Binance Geographic Restriction Muammosi:
- Uzbekistan'dan Binance'ga ulanib bo'lmaydi
- YECHIM: VPN ishlatish yoki boshqa crypto exchange'dan foydalanish

### Telegram Xatosi:
- Token to'g'rimi? Bot @BotFather orqali yaratildi mi?
- Chat ID to'g'rimi? (raqam bo'lishi kerak)

### Python Versiyasi:
- Railway avtomatik Python 3.11/3.12 ishlatadi (OK)

---

## 📝 QANDAY ISHLAYDI?

Bot har 1 soatda:
1. BTC narxini Binance'dan oladi
2. Oxirgi 14 soatning ma'lumotini tahlil qiladi
3. Signal yuboradi (SOTISH / SOTIB OLISH)
4. Telegram'ga xabar yuboradi

Xatolar avtomatik qayd qilinadi va Telegram'ga yuboriladi.

---

## 🛠️ LOCALHOST'DA TEST QILISH

```bash
# .env fayli yarating
echo "BINANCE_API_KEY=your_key" > .env
echo "BINANCE_API_SECRET=your_secret" >> .env
echo "TELEGRAM_TOKEN=your_token" >> .env
echo "CHAT_ID=your_chat_id" >> .env

# Requirements o'rnatish
pip install -r requirements.txt

# Bot'ni ishga tushirish
python main.py
```

Savollaringiz bo'lsa, menga yozavering! 🚀
