import os
import time
import json
import logging
import requests
from datetime import datetime
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

TOP_N = 20              # Eng volatile N ta coin
POSITION_SIZE = 50      # Har bir coin uchun USDT
LEVERAGE = 4
STOP_LOSS_PERCENT = 2
TAKE_PROFIT_PERCENT = 6
CONFIDENCE_THRESHOLD = 65

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
ACTIVE_POSITIONS = {}  # {symbol: position}


def get_volatile_symbols(n=TOP_N):
    """Binance Futures'dan real vaqtda eng volatile N ta coin"""
    try:
        tickers = client.futures_ticker()
        usdt_pairs = [
            t for t in tickers
            if t['symbol'].endswith('USDT')
            and float(t['quoteVolume']) > 5_000_000  # Min $5M hajm
        ]
        # Absolut % o'zgarish bo'yicha saralash
        usdt_pairs.sort(key=lambda x: abs(float(x['priceChangePercent'])), reverse=True)
        symbols = [t['symbol'] for t in usdt_pairs[:n]]
        logger.info(f"🔥 Top {n} volatile: {', '.join(symbols)}")
        return symbols
    except Exception as e:
        logger.error(f"❌ Volatile symbols xatosi: {e}")
        # Fallback
        return ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]


def send_telegram(msg):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": CHAT_ID, "text": msg}, timeout=10)
    except Exception as e:
        logger.error(f"❌ Telegram xatosi: {e}")


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
        if down == 0:
            rsi = 100
        else:
            rs = up / down
            rsi = 100 - (100 / (1 + rs))
    return rsi


def get_market_data(symbol):
    try:
        ticker = client.futures_symbol_ticker(symbol=symbol)
        current_price = float(ticker['price'])

        klines = client.futures_klines(symbol=symbol, interval='1h', limit=24)
        closes = [float(k[4]) for k in klines]
        highs = [float(k[2]) for k in klines]
        lows = [float(k[3]) for k in klines]
        volumes = [float(k[7]) for k in klines]

        highest_high_4h = max(highs[-4:])
        lowest_low_4h = min(lows[-4:])
        avg_volume_4h = sum(volumes[-4:]) / 4
        volume_spike = volumes[-1] / avg_volume_4h if avg_volume_4h > 0 else 1

        return {
            "symbol": symbol,
            "current_price": current_price,
            "highest_high_4h": highest_high_4h,
            "lowest_low_4h": lowest_low_4h,
            "avg_volume_4h": avg_volume_4h,
            "volume_spike": volume_spike,
            "current_volume": volumes[-1],
            "price_change_4h": ((closes[-1] - closes[-4]) / closes[-4]) * 100 if closes[-4] != 0 else 0,
            "rsi": calculate_rsi(closes)
        }
    except Exception as e:
        logger.error(f"❌ {symbol} market data xatosi: {e}")
        return None


def analyze_with_claude(market_data):
    try:
        symbol = market_data['symbol']
        prompt = f"""
Sen professional Smart Money Futures trader. {symbol} uchun SHORT signal ber.

Market Data:
- Symbol: {symbol}
- Current Price: ${market_data['current_price']:,.4f}
- Highest High (4h): ${market_data['highest_high_4h']:,.4f}
- Lowest Low (4h): ${market_data['lowest_low_4h']:,.4f}
- Price Change (4h): {market_data['price_change_4h']:.2f}%
- RSI: {market_data['rsi']:.2f}
- Volume Spike: {market_data['volume_spike']:.2f}x

Smart Money analiz: Liquidity, Supply/Demand, Order Flow, Market Structure, Volume.
Position: {POSITION_SIZE} USDT | Leverage: {LEVERAGE}x | SL: {STOP_LOSS_PERCENT}% | TP: {TAKE_PROFIT_PERCENT}%

FAQAT JSON (O'zbek tilida):
{{
    "action": "SHORT" yoki "HOLD",
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

        logger.error(f"❌ Claude API xatosi ({symbol}): {response.text}")
        return None

    except Exception as e:
        logger.error(f"❌ Claude analiz xatosi ({symbol}): {e}")
        return None


def open_position(symbol, analysis):
    global ACTIVE_POSITIONS

    if symbol in ACTIVE_POSITIONS:
        return False

    entry = float(analysis['entry_price'])
    sl = float(analysis['stop_loss'])
    tp = float(analysis['take_profit'])
    quantity = round(POSITION_SIZE * LEVERAGE / entry, 4)
    risk = POSITION_SIZE * (STOP_LOSS_PERCENT / 100)

    position = {
        "timestamp": datetime.now().isoformat(),
        "symbol": symbol,
        "type": "SHORT",
        "status": "OPEN",
        "entry_price": entry,
        "stop_loss": sl,
        "take_profit": tp,
        "quantity": quantity,
        "confidence": analysis['confidence'],
        "reason": analysis['reason'],
        "risk_amount": risk,
        "risk_reward": analysis['risk_reward_ratio'],
        "pnl": 0
    }

    ACTIVE_POSITIONS[symbol] = position
    TRADES.append(position)

    msg = f"""
🔴 SHORT SIGNAL: {symbol}
{'━' * 35}
📊 Entry:       ${entry:,.4f}
🎯 Take Profit: ${tp:,.4f}
🛑 Stop Loss:   ${sl:,.4f}
💰 Size: ${POSITION_SIZE} | Leverage: {LEVERAGE}x
💸 Risk: ${risk:.2f}
📈 R/R: {analysis['risk_reward_ratio']:.2f}
💪 Confidence: {analysis['confidence']}%
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💡 {analysis['reason']}
🕐 {position['timestamp'][:19]}
"""
    send_telegram(msg)
    logger.info(f"🔴 SHORT ochildi: {symbol} @ ${entry:,.4f}")
    return True


def monitor_positions():
    global ACTIVE_POSITIONS

    to_close = []

    for symbol, pos in ACTIVE_POSITIONS.items():
        try:
            ticker = client.futures_symbol_ticker(symbol=symbol)
            current_price = float(ticker['price'])

            entry = pos['entry_price']
            pnl_pct = ((entry - current_price) / entry) * 100
            pnl_amt = pnl_pct * POSITION_SIZE / 100
            pos['pnl'] = pnl_amt

            if current_price <= pos['take_profit']:
                to_close.append((symbol, "TAKE_PROFIT", current_price))
            elif current_price >= pos['stop_loss']:
                to_close.append((symbol, "STOP_LOSS", current_price))

        except Exception as e:
            logger.error(f"❌ Monitor xatosi ({symbol}): {e}")

    for symbol, reason, price in to_close:
        close_position(symbol, reason, price)


def close_position(symbol, reason, current_price):
    global ACTIVE_POSITIONS

    pos = ACTIVE_POSITIONS.pop(symbol, None)
    if not pos:
        return

    entry = pos['entry_price']
    pnl_pct = ((entry - current_price) / entry) * 100
    pnl_amt = pnl_pct * POSITION_SIZE / 100
    emoji = "✅" if pnl_amt > 0 else "❌"

    msg = f"""
{emoji} POSITION YOPILDI: {symbol}
{'━' * 35}
🎯 Reason: {reason}
Entry: ${entry:,.4f}
Exit:  ${current_price:,.4f}
{'🟢' if pnl_amt > 0 else '🔴'} PnL: {pnl_pct:+.2f}% (${pnl_amt:+,.2f})
🕐 {datetime.now().isoformat()[:19]}
"""
    send_telegram(msg)
    logger.info(f"{emoji} {symbol} yopildi: {reason} | PnL: {pnl_pct:+.2f}%")


def print_stats():
    closed = [t for t in TRADES if t['status'] == 'CLOSED']
    if not closed:
        return
    wins = sum(1 for t in closed if t['pnl'] > 0)
    total_pnl = sum(t['pnl'] for t in closed)
    logger.info(f"📊 Stats: {len(closed)} trades | {wins} win | PnL: ${total_pnl:+,.2f}")


def trading_loop():
    logger.info("🚀 Smart Money AI Futures Agent ishga tushdi!")
    logger.info(f"📋 Har siklda TOP {TOP_N} volatile coin tahlil qilinadi")
    logger.info(f"💰 Har bir coin uchun: ${POSITION_SIZE} USDT | {LEVERAGE}x leverage")

    send_telegram(f"""
🚀 Smart Money AI Futures Agent ishga tushdi!
{'━' * 35}
🔥 Har siklda TOP {TOP_N} volatile coin
💰 Har bir coin: ${POSITION_SIZE} USDT ({LEVERAGE}x)
🎯 Faqat SHORT signallar
⏰ Har 5 daqiqada tahlil
🛑 Stop Loss: {STOP_LOSS_PERCENT}% | TP: {TAKE_PROFIT_PERCENT}%
📊 Min confidence: {CONFIDENCE_THRESHOLD}%
""")

    while True:
        try:
            # Ochiq positionlarni kuzat
            if ACTIVE_POSITIONS:
                monitor_positions()

            # Real vaqtda eng volatile coinlarni ol
            symbols = get_volatile_symbols(TOP_N)

            # Har bir coinni tahlil qil
            for symbol in symbols:
                if symbol in ACTIVE_POSITIONS:
                    logger.info(f"⏭️ {symbol} — ochiq position bor, o'tkazildi")
                    continue

                market_data = get_market_data(symbol)
                if not market_data:
                    continue

                analysis = analyze_with_claude(market_data)
                if not analysis:
                    continue

                logger.info(f"📊 {symbol}: {analysis['action']} | Confidence: {analysis['confidence']}% | RSI: {market_data['rsi']:.1f}")

                if analysis['action'] == 'SHORT' and analysis['confidence'] >= CONFIDENCE_THRESHOLD:
                    open_position(symbol, analysis)

                # Claude rate limit uchun kutish
                time.sleep(3)

            print_stats()
            logger.info(f"⏳ 5 minutdan keyin yana tahlil... | Ochiq: {len(ACTIVE_POSITIONS)} position | Tahlil: {len(symbols)} coin")
            time.sleep(300)

        except Exception as e:
            logger.error(f"❌ Loop xatosi: {e}")
            send_telegram(f"❌ Bot xatosi: {e}")
            time.sleep(60)


if __name__ == "__main__":
    trading_loop()
