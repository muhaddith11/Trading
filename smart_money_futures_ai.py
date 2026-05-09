import os
import time
import json
import logging
import requests
import threading
from datetime import datetime, timedelta
from binance.client import Client
from binance.exceptions import BinanceAPIException

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

API_KEY = os.environ.get('BINANCE_API_KEY')
API_SECRET = os.environ.get('BINANCE_API_SECRET')
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
CHAT_ID = os.environ.get('CHAT_ID')
CLAUDE_API_KEY = os.environ.get('CLAUDE_API_KEY')

TOP_N = 20
LEVERAGE = 4
STOP_LOSS_PERCENT = 3
TAKE_PROFIT_PERCENT = 10
CONFIDENCE_THRESHOLD = 75
BALANCE_PERCENT = 0.25  # Har savdoga balansning 25%

if not all([API_KEY, API_SECRET, TELEGRAM_TOKEN, CHAT_ID, CLAUDE_API_KEY]):
    logger.error("❌ Environment variables to'liq emas!")
    exit(1)

try:
    client = Client(API_KEY, API_SECRET)
    logger.info("✅ Binance Futures API ulanish muvaffaqiyatli")
except Exception as e:
    logger.error(f"❌ Binance xatosi: {e}")
    exit(1)

TRADES = []
ACTIVE_POSITIONS = {}
BOT_RUNNING = True
LAST_REPORT_DATE = None
TELEGRAM_OFFSET = 0


# ─── TELEGRAM ────────────────────────────────────────────────────────────────

def send_telegram(msg, chat_id=None):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={
            "chat_id": chat_id or CHAT_ID,
            "text": msg,
            "parse_mode": "HTML"
        }, timeout=10)
    except Exception as e:
        logger.error(f"❌ Telegram xatosi: {e}")


def get_telegram_updates():
    global TELEGRAM_OFFSET
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
        resp = requests.get(url, params={"offset": TELEGRAM_OFFSET, "timeout": 5}, timeout=10)
        if resp.status_code == 200:
            return resp.json().get("result", [])
    except Exception:
        pass
    return []


def handle_command(text, chat_id):
    text = text.strip().lower()

    if text == "/status":
        if not ACTIVE_POSITIONS:
            send_telegram("📭 Hozir ochiq position yo'q", chat_id)
        else:
            msg = "📊 <b>Ochiq Positionlar:</b>\n" + "━" * 30 + "\n"
            for sym, pos in ACTIVE_POSITIONS.items():
                try:
                    ticker = client.futures_symbol_ticker(symbol=sym)
                    cur = float(ticker['price'])
                    entry = pos['entry_price']
                    if pos['type'] == 'SHORT':
                        pnl_pct = ((entry - cur) / entry) * 100
                    else:
                        pnl_pct = ((cur - entry) / entry) * 100
                    pnl_amt = pnl_pct * POSITION_SIZE / 100
                    emoji = "🟢" if pnl_amt > 0 else "🔴"
                    msg += f"{emoji} <b>{sym}</b> ({pos['type']})\n"
                    msg += f"   Entry: ${entry:,.4f} → Hozir: ${cur:,.4f}\n"
                    msg += f"   PnL: {pnl_pct:+.2f}% (${pnl_amt:+,.2f})\n\n"
                except Exception:
                    msg += f"📌 {sym} ({pos['type']}) - ma'lumot olib bo'lmadi\n\n"
            send_telegram(msg, chat_id)

    elif text == "/stats":
        closed = [t for t in TRADES if t.get('status') == 'CLOSED']
        if not closed:
            send_telegram("📭 Hali yopilgan savdo yo'q", chat_id)
        else:
            wins = [t for t in closed if t['pnl'] > 0]
            losses = [t for t in closed if t['pnl'] <= 0]
            total_pnl = sum(t['pnl'] for t in closed)
            win_rate = len(wins) / len(closed) * 100
            msg = f"""📈 <b>Trading Statistika</b>
{'━' * 30}
📊 Jami savdolar: {len(closed)}
✅ Wins: {len(wins)} | ❌ Losses: {len(losses)}
🎯 Win Rate: {win_rate:.1f}%
💰 Jami PnL: ${total_pnl:+,.2f}
📌 Ochiq: {len(ACTIVE_POSITIONS)} position"""
            send_telegram(msg, chat_id)

    elif text == "/stop":
        global BOT_RUNNING
        BOT_RUNNING = False
        send_telegram("🛑 Bot to'xtatilmoqda...", chat_id)

    elif text == "/top":
        symbols = get_volatile_symbols(TOP_N)
        msg = f"🔥 <b>Hozirgi TOP {TOP_N} volatile coinlar:</b>\n\n"
        msg += "\n".join([f"• {s}" for s in symbols])
        send_telegram(msg, chat_id)

    elif text == "/help":
        msg = """🤖 <b>Bot buyruqlari:</b>
━━━━━━━━━━━━━━━━━━━━━
/status — ochiq positionlar
/stats  — umumiy statistika
/top    — hozirgi top coinlar
/stop   — botni to'xtatish
/help   — yordam"""
        send_telegram(msg, chat_id)


def telegram_listener():
    global TELEGRAM_OFFSET
    logger.info("📱 Telegram listener ishga tushdi")
    while BOT_RUNNING:
        try:
            updates = get_telegram_updates()
            for update in updates:
                TELEGRAM_OFFSET = update['update_id'] + 1
                msg = update.get('message', {})
                text = msg.get('text', '')
                chat_id = str(msg.get('chat', {}).get('id', ''))
                if text.startswith('/'):
                    handle_command(text, chat_id)
            time.sleep(2)
        except Exception as e:
            logger.error(f"❌ Telegram listener xatosi: {e}")
            time.sleep(5)


# ─── MARKET ──────────────────────────────────────────────────────────────────

def get_free_balance():
    """Binance Futures'dagi bo'sh USDT balansini olish"""
    try:
        account = client.futures_account_balance()
        for asset in account:
            if asset['asset'] == 'USDT':
                balance = float(asset['availableBalance'])
                logger.info(f"💰 Bo'sh balans: ${balance:.2f} USDT")
                return balance
        return 0
    except Exception as e:
        logger.error(f"❌ Balans olish xatosi: {e}")
        return 0


def get_volatile_symbols(n=TOP_N):
    try:
        tickers = client.futures_ticker()
        usdt_pairs = [
            t for t in tickers
            if t['symbol'].endswith('USDT')
            and float(t['quoteVolume']) > 5_000_000
        ]
        usdt_pairs.sort(key=lambda x: abs(float(x['priceChangePercent'])), reverse=True)
        symbols = [t['symbol'] for t in usdt_pairs[:n]]
        logger.info(f"🔥 Top {n} volatile: {', '.join(symbols)}")
        return symbols
    except Exception as e:
        logger.error(f"❌ Volatile symbols xatosi: {e}")
        return ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]


def calculate_rsi(prices, period=14):
    if len(prices) < period:
        return 50
    deltas = [prices[i] - prices[i-1] for i in range(1, len(prices))]
    seed = deltas[:period]
    up = sum(x for x in seed if x > 0) / period
    down = -sum(x for x in seed if x < 0) / period
    if down == 0:
        return 100
    rs = up / down
    rsi = 100 - (100 / (1 + rs))
    for i in range(period, len(deltas)):
        delta = deltas[i]
        up = (up * 13 + (delta if delta > 0 else 0)) / 14
        down = (down * 13 + (-delta if delta < 0 else 0)) / 14
        rs = up / down if down != 0 else 0
        rsi = 100 - (100 / (1 + rs))
    return rsi


def get_market_data(symbol):
    try:
        ticker = client.futures_symbol_ticker(symbol=symbol)
        current_price = float(ticker['price'])

        # 1h ma'lumot
        klines_1h = client.futures_klines(symbol=symbol, interval='1h', limit=24)
        closes_1h = [float(k[4]) for k in klines_1h]
        highs_1h = [float(k[2]) for k in klines_1h]
        lows_1h = [float(k[3]) for k in klines_1h]
        volumes_1h = [float(k[7]) for k in klines_1h]

        # 15m ma'lumot
        klines_15m = client.futures_klines(symbol=symbol, interval='15m', limit=24)
        closes_15m = [float(k[4]) for k in klines_15m]
        volumes_15m = [float(k[7]) for k in klines_15m]

        # 4h ma'lumot
        klines_4h = client.futures_klines(symbol=symbol, interval='4h', limit=12)
        closes_4h = [float(k[4]) for k in klines_4h]
        highs_4h = [float(k[2]) for k in klines_4h]
        lows_4h = [float(k[3]) for k in klines_4h]
        volumes_4h = [float(k[7]) for k in klines_4h]

        avg_vol_1h = sum(volumes_1h[-4:]) / 4
        avg_vol_15m = sum(volumes_15m[-4:]) / 4
        avg_vol_4h = sum(volumes_4h[-3:]) / 3
        vol_spike_1h = volumes_1h[-1] / avg_vol_1h if avg_vol_1h > 0 else 1
        vol_spike_15m = volumes_15m[-1] / avg_vol_15m if avg_vol_15m > 0 else 1
        vol_spike_4h = volumes_4h[-1] / avg_vol_4h if avg_vol_4h > 0 else 1

        return {
            "symbol": symbol,
            "current_price": current_price,
            "highest_high_4h": max(highs_4h[-3:]),
            "lowest_low_4h": min(lows_4h[-3:]),
            "price_change_15m": ((closes_15m[-1] - closes_15m[-2]) / closes_15m[-2]) * 100 if closes_15m[-2] != 0 else 0,
            "price_change_1h": ((closes_1h[-1] - closes_1h[-2]) / closes_1h[-2]) * 100 if closes_1h[-2] != 0 else 0,
            "price_change_4h": ((closes_4h[-1] - closes_4h[-2]) / closes_4h[-2]) * 100 if closes_4h[-2] != 0 else 0,
            "rsi_15m": calculate_rsi(closes_15m),
            "rsi_1h": calculate_rsi(closes_1h),
            "rsi_4h": calculate_rsi(closes_4h),
            "vol_spike_15m": vol_spike_15m,
            "vol_spike_1h": vol_spike_1h,
            "vol_spike_4h": vol_spike_4h,
        }
    except Exception as e:
        logger.error(f"❌ {symbol} market data xatosi: {e}")
        return None


# ─── CLAUDE AI ───────────────────────────────────────────────────────────────

def analyze_with_claude(market_data):
    try:
        symbol = market_data['symbol']
        prompt = f"""Sen professional Smart Money Futures trader. {symbol} uchun signal ber.

MULTI-TIMEFRAME MA'LUMOT:
Symbol: {symbol}
Narx: ${market_data['current_price']:,.6f}

📊 4H Timeframe (asosiy trend):
- RSI (4h): {market_data['rsi_4h']:.2f}
- Volume Spike (4h): {market_data['vol_spike_4h']:.2f}x
- Narx o'zgarish (4h): {market_data['price_change_4h']:.2f}%
- Highest High (4h): ${market_data['highest_high_4h']:,.6f}
- Lowest Low (4h): ${market_data['lowest_low_4h']:,.6f}

📊 1H Timeframe (kirish zona):
- RSI (1h): {market_data['rsi_1h']:.2f}
- Volume Spike (1h): {market_data['vol_spike_1h']:.2f}x
- Narx o'zgarish (1h): {market_data['price_change_1h']:.2f}%

📊 15M Timeframe (aniq kirish):
- RSI (15m): {market_data['rsi_15m']:.2f}
- Volume Spike (15m): {market_data['vol_spike_15m']:.2f}x
- Narx o'zgarish (15m): {market_data['price_change_15m']:.2f}%

Smart Money tahlil: Liquidity, Supply/Demand, Order Flow, Market Structure.
Size: {POSITION_SIZE} USDT | Leverage: {LEVERAGE}x | SL: {STOP_LOSS_PERCENT}% | TP: {TAKE_PROFIT_PERCENT}%

MUHIM QOIDA:
- Faqat narx {TAKE_PROFIT_PERCENT}% yurishi ANIQ bo'lganda LONG yoki SHORT ber
- Agar {TAKE_PROFIT_PERCENT}% yurish ko'rinmasa — HOLD ber
- Take profit = entry narxdan aynan {TAKE_PROFIT_PERCENT}% uzoqda bo'lsin
- Confidence = shu {TAKE_PROFIT_PERCENT}% yurish bo'lishiga ishonch darajasi

FAQAT JSON (O'zbek tilida), boshqa hech narsa yozmang:
{{
    "action": "LONG" yoki "SHORT" yoki "HOLD",
    "confidence": 0-100,
    "reason": "sabab",
    "entry_price": {market_data['current_price']},
    "stop_loss": float,
    "take_profit": float,
    "risk_reward_ratio": float
}}"""

        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": CLAUDE_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-sonnet-4-6",
                "max_tokens": 600,
                "messages": [{"role": "user", "content": prompt}]
            },
            timeout=30
        )

        if response.status_code == 200:
            text = response.json()['content'][0]['text']
            json_start = text.find('{')
            json_end = text.rfind('}') + 1
            if json_start != -1 and json_end > json_start:
                return json.loads(text[json_start:json_end])

        # Kredit tugagan bo'lsa Telegram'ga xabar yuborish
        error_text = response.text
        if 'credit balance is too low' in error_text or 'insufficient_quota' in error_text:
            send_telegram(
                "⚠️ <b>DIQQAT: Claude API krediti tugadi!</b>\n\n"
                "Bot ishlashni to'xtatdi.\n"
                "console.anthropic.com/settings/billing da kredit soling."
            )
            logger.error("⚠️ Claude API krediti tugadi! Telegram xabar yuborildi.")

        logger.error(f"❌ Claude API xatosi ({symbol}): {error_text[:200]}")
        return None

    except Exception as e:
        logger.error(f"❌ Claude analiz xatosi ({symbol}): {e}")
        return None


# ─── POSITION MANAGEMENT ─────────────────────────────────────────────────────

def open_position(symbol, analysis, position_size):
    if symbol in ACTIVE_POSITIONS:
        return False

    action = analysis['action']
    entry = float(analysis['entry_price'])
    sl = float(analysis['stop_loss'])
    tp = float(analysis['take_profit'])
    quantity = round(position_size * LEVERAGE / entry, 4)
    risk = position_size * (STOP_LOSS_PERCENT / 100)

    position = {
        "timestamp": datetime.now().isoformat(),
        "symbol": symbol,
        "type": action,
        "status": "OPEN",
        "entry_price": entry,
        "stop_loss": sl,
        "take_profit": tp,
        "quantity": quantity,
        "confidence": analysis['confidence'],
        "reason": analysis['reason'],
        "position_size": position_size,
        "risk_amount": risk,
        "risk_reward": analysis.get('risk_reward_ratio', 0),
        "pnl": 0
    }

    ACTIVE_POSITIONS[symbol] = position
    TRADES.append(position)

    emoji = "🔴" if action == "SHORT" else "🟢"
    msg = f"""
{emoji} <b>{action} SIGNAL: {symbol}</b>
{'━' * 35}
📊 Entry:       ${entry:,.6f}
🎯 Take Profit: ${tp:,.6f}
🛑 Stop Loss:   ${sl:,.6f}
💰 Size: ${position_size} | Leverage: {LEVERAGE}x | Exposure: ${position_size * LEVERAGE:.2f}
💸 Risk: ${risk:.2f}
📈 R/R: {analysis.get('risk_reward_ratio', 0):.2f}
💪 Confidence: {analysis['confidence']}%
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💡 {analysis['reason']}
🕐 {position['timestamp'][:19]}
"""
    send_telegram(msg)
    logger.info(f"{emoji} {action} ochildi: {symbol} @ ${entry:,.6f}")
    return True


def monitor_positions():
    to_close = []
    for symbol, pos in ACTIVE_POSITIONS.items():
        try:
            ticker = client.futures_symbol_ticker(symbol=symbol)
            cur = float(ticker['price'])
            entry = pos['entry_price']

            if pos['type'] == 'SHORT':
                pnl_pct = ((entry - cur) / entry) * 100
                hit_tp = cur <= pos['take_profit']
                hit_sl = cur >= pos['stop_loss']
            else:  # LONG
                pnl_pct = ((cur - entry) / entry) * 100
                hit_tp = cur >= pos['take_profit']
                hit_sl = cur <= pos['stop_loss']

            pos['pnl'] = pnl_pct * POSITION_SIZE / 100

            if hit_tp:
                to_close.append((symbol, "TAKE_PROFIT", cur))
            elif hit_sl:
                to_close.append((symbol, "STOP_LOSS", cur))

        except Exception as e:
            logger.error(f"❌ Monitor xatosi ({symbol}): {e}")

    for symbol, reason, price in to_close:
        close_position(symbol, reason, price)


def close_position(symbol, reason, current_price):
    pos = ACTIVE_POSITIONS.pop(symbol, None)
    if not pos:
        return

    entry = pos['entry_price']
    if pos['type'] == 'SHORT':
        pnl_pct = ((entry - current_price) / entry) * 100
    else:
        pnl_pct = ((current_price - entry) / entry) * 100

    pnl_amt = pnl_pct * pos.get('position_size', 50) / 100
    pos['status'] = 'CLOSED'
    pos['pnl'] = pnl_amt
    emoji = "✅" if pnl_amt > 0 else "❌"

    msg = f"""
{emoji} <b>POSITION YOPILDI: {symbol}</b>
{'━' * 35}
🎯 Sabab: {reason}
📊 {pos['type']}: ${entry:,.6f} → ${current_price:,.6f}
{'🟢' if pnl_amt > 0 else '🔴'} PnL: {pnl_pct:+.2f}% (${pnl_amt:+,.2f})
🕐 {datetime.now().isoformat()[:19]}
"""
    send_telegram(msg)
    logger.info(f"{emoji} {symbol} yopildi: {reason} | PnL: {pnl_pct:+.2f}%")


# ─── DAILY REPORT ─────────────────────────────────────────────────────────────

def send_daily_report():
    global LAST_REPORT_DATE
    now = datetime.utcnow()

    if LAST_REPORT_DATE == now.date():
        return
    if now.hour != 19:  # Har kuni soat 19:00 UTC (00:00 Toshkent)
        return

    LAST_REPORT_DATE = now.date()
    today = now.date()

    today_trades = [
        t for t in TRADES
        if t.get('status') == 'CLOSED'
        and t['timestamp'][:10] == str(today)
    ]

    if not today_trades:
        send_telegram(f"📊 <b>Kunlik hisobot ({today})</b>\n\nBugun savdo bo'lmadi.")
        return

    wins = [t for t in today_trades if t['pnl'] > 0]
    losses = [t for t in today_trades if t['pnl'] <= 0]
    total_pnl = sum(t['pnl'] for t in today_trades)
    win_rate = len(wins) / len(today_trades) * 100

    msg = f"""📊 <b>Kunlik hisobot — {today}</b>
{'━' * 35}
📈 Jami savdolar: {len(today_trades)}
✅ Wins: {len(wins)} | ❌ Losses: {len(losses)}
🎯 Win Rate: {win_rate:.1f}%
💰 Kunlik PnL: ${total_pnl:+,.2f}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📌 Ochiq positionlar: {len(ACTIVE_POSITIONS)}"""
    send_telegram(msg)


# ─── MAIN LOOP ────────────────────────────────────────────────────────────────

def trading_loop():
    logger.info("🚀 Smart Money AI Futures Agent ishga tushdi!")
    logger.info(f"📋 Har siklda TOP {TOP_N} volatile coin tahlil qilinadi")
    logger.info(f"💰 Har bir coin: ${POSITION_SIZE} USDT | {LEVERAGE}x | Min confidence: {CONFIDENCE_THRESHOLD}%")

    send_telegram(f"""
🚀 <b>Smart Money AI Futures Agent ishga tushdi!</b>
{'━' * 35}
🔥 Har siklda TOP {TOP_N} volatile coin
💰 Har bir coin: ${POSITION_SIZE} USDT ({LEVERAGE}x)
🎯 LONG va SHORT signallar
⏰ Har 2 soatda tahlil (15m+1h+4h)
💪 Min confidence: {CONFIDENCE_THRESHOLD}%
🛑 Stop Loss: {STOP_LOSS_PERCENT}% | TP: {TAKE_PROFIT_PERCENT}%
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📱 Buyruqlar: /help""")

    # Telegram listener alohida threadda
    listener_thread = threading.Thread(target=telegram_listener, daemon=True)
    listener_thread.start()

    while BOT_RUNNING:
        try:
            if ACTIVE_POSITIONS:
                monitor_positions()

            send_daily_report()

            # Haqiqiy balansni ol va 25% hisoblа
            free_balance = get_free_balance()
            position_size = round(free_balance * BALANCE_PERCENT, 2)

            if position_size < 5:
                logger.warning(f"⚠️ Balans juda kam: ${free_balance:.2f} → savdo qilib bo'lmaydi")
                send_telegram(f"⚠️ Balans juda kam: ${free_balance:.2f}\nMinimal $20 USDT kerak.")
                time.sleep(7200)
                continue

            logger.info(f"📐 Position size: ${position_size} (balans ${free_balance:.2f} ning 25%) × {LEVERAGE}x = ${position_size * LEVERAGE:.2f} exposure")

            symbols = get_volatile_symbols(TOP_N)

            for symbol in symbols:
                if not BOT_RUNNING:
                    break

                if symbol in ACTIVE_POSITIONS:
                    logger.info(f"⏭️ {symbol} — ochiq position bor")
                    continue

                market_data = get_market_data(symbol)
                if not market_data:
                    continue

                analysis = analyze_with_claude(market_data)
                if not analysis:
                    continue

                action = analysis.get('action', 'HOLD')
                confidence = analysis.get('confidence', 0)

                logger.info(f"📊 {symbol}: {action} | {confidence}% | RSI 4h:{market_data['rsi_4h']:.1f} 1h:{market_data['rsi_1h']:.1f} 15m:{market_data['rsi_15m']:.1f}")

                if action in ('LONG', 'SHORT') and confidence >= CONFIDENCE_THRESHOLD:
                    open_position(symbol, analysis, position_size)

                time.sleep(3)

            closed = [t for t in TRADES if t.get('status') == 'CLOSED']
            wins = sum(1 for t in closed if t['pnl'] > 0)
            total_pnl = sum(t['pnl'] for t in closed)
            logger.info(f"⏳ 2 soat kutish | Ochiq: {len(ACTIVE_POSITIONS)} | Jami PnL: ${total_pnl:+,.2f} | Wins: {wins}/{len(closed)}")
            time.sleep(7200)

        except Exception as e:
            logger.error(f"❌ Loop xatosi: {e}")
            send_telegram(f"❌ Bot xatosi: {e}")
            time.sleep(60)

    send_telegram("🛑 Bot to'xtatildi.")
    logger.info("🛑 Bot to'xtatildi.")


if __name__ == "__main__":
    trading_loop()
