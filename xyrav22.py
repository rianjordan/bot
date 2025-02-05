import aiohttp
import asyncio
from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, CallbackContext
import json
import logging
from datetime import datetime, timedelta
from aiolimiter import AsyncLimiter
import signal
import sys
import functools
from collections import Counter
import requests  # Impor dari news.py
from urllib.parse import urlparse  # Impor dari news.py
import threading
import schedule
import time
from datetime import datetime, timedelta, UTC

config_file = "config.json"

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Global variables to track the bot's state
is_paused = False
start_time = datetime.now()
total_notifications_sent = 0
error_count = 0
pair_notifications = Counter()
maintenance_coins = set()

def signal_handler(sig, frame, bot_token, chat_id):
    logger.info("Signal handler called with signal: %s", sig)
    asyncio.run(send_telegram_message("Xyrabot is shutting down", bot_token, chat_id))
    sys.exit(0)

async def send_market_summary(update: Update, context: CallbackContext):
    await update.message.reply_text("Market summary not implemented yet.")

async def send_stats(update: Update, context: CallbackContext):
    await update.message.reply_text("Stats not implemented yet.")

async def send_news(update: Update, context: CallbackContext):
    await update.message.reply_text("Fetching news...")
    bot_token = config["bot_token"]
    chat_id = config["chat_id"]
    await my_custom_function(bot_token, chat_id)  # Panggil fungsi dengan parameter yang diperlukan

def load_config():
    try:
        with open(config_file, "r") as f:
            config = json.load(f)
        return config
    except FileNotFoundError:
        return None

def save_config(config):
    with open(config_file, "w") as f:
        json.dump(config, f)

async def send_telegram_message(message, bot_token, chat_id):
    global total_notifications_sent
    try:
        bot = Bot(token=bot_token)
        
        # Jika pesan terlalu panjang, bagi menjadi beberapa bagian
        max_length = 4096
        if len(message) > max_length:
            parts = [message[i:i + max_length] for i in range(0, len(message), max_length)]
            for part in parts:
                await bot.send_message(chat_id=chat_id, text=part, parse_mode="HTML")
                total_notifications_sent += 1
                logger.info("Sending Notification Part")
        else:
            await bot.send_message(chat_id=chat_id, text=message, parse_mode="HTML")
            total_notifications_sent += 1
            logger.info("Sending Notification")
    except Exception as e:
        logger.error(f"Error sending message: {str(e)}")
        global error_count
        error_count += 1

async def get_all_crypto_data():
    api_url = 'https://indodax.com/api/summaries'
    async with aiohttp.ClientSession() as session:
        async with session.get(api_url) as response:
            if response.status == 200:
                data = await response.json()
                return data['tickers']
            else:
                logger.error(f"Failed to fetch data. Status code: {response.status}")
                return None

async def get_summary_data():
    api_url = 'https://indodax.com/api/summaries'
    async with aiohttp.ClientSession() as session:
        async with session.get(api_url) as response:
            if response.status == 200:
                data = await response.json()
                return data
            else:
                logger.error(f"Failed to fetch data. Status code: {response.status}")
                return None

rate_limiter = AsyncLimiter(70, 30)  # Rate limit to 70 requests per 30 seconds

async def api_limiter():
    async with rate_limiter:
        await asyncio.sleep(0)

def safe_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0

def admin_only(func):
    @functools.wraps(func)
    async def wrapper(update: Update, context: CallbackContext, *args, **kwargs):
        if update.effective_chat.id != int(config['chat_id']):
            await update.message.reply_text("You are not authorized to use this command.")
            return
        return await func(update, context, *args, **kwargs)
    return wrapper

@admin_only
async def pause(update: Update, context: CallbackContext):
    global is_paused
    if is_paused:
        await update.message.reply_text("Bot is already paused.")
    else:
        logger.info("Pausing bot monitoring")
        is_paused = True
        await update.message.reply_text("Xyrabot is paused")

@admin_only
async def resume(update: Update, context: CallbackContext):
    global is_paused
    if not is_paused:
        await update.message.reply_text("Bot is already running.")
    else:
        logger.info("Resuming bot monitoring")
        is_paused = False
        await update.message.reply_text("Xyrabot back for monitoring")

def format_pair(pair):
    """Mengganti IDR dan USDT dengan format yang benar"""
    if pair.endswith("IDR"):
        return pair.replace("IDR", "/IDR")
    elif pair.endswith("USDT"):
        return pair.replace("USDT", "/USDT")
    return pair

# Fungsi dari news.py
def get_domain_from_url(url):
    """
    Fungsi untuk mengekstrak nama domain dari URL.
    Contoh: https://www.beritasatu.com/ekonomi/... -> beritasatu.com
    """
    parsed_url = urlparse(url)
    domain = parsed_url.netloc
    return domain

async def my_custom_function(bot_token, chat_id):
    try:
        url = "https://api.worldnewsapi.com/search-news?text=kripto+bitcoin&source-countries=ID"
        api_key = "df5d81e9b8474ab8a378235e45ec1792"
        headers = {'x-api-key': api_key}
        response = requests.get(url, headers=headers)

        if response.status_code == 200:
            news_data = response.json()
            all_news_messages = []

            for news in news_data['news']:
                title = news.get('title', 'No Title')
                url = news.get('url', '#')
                publish_date = news.get('publish_date', 'Unknown Date')
                source = news.get('source', {}).get('name', None)
                
                if not source:
                    source = get_domain_from_url(url)
                
                news_message = (
                    f"<a href='{url}'>{title}</a> (Source: {source})\n"
                    f"Publish Date: {publish_date}\n"
                    "-------------------------"
                )
                all_news_messages.append(news_message)

            return all_news_messages
        else:
            logger.error(f"Failed to fetch news. Status code: {response.status_code}")
            return ["⚠️ Gagal mengambil berita. Silakan coba lagi nanti."]
    except Exception as e:
        logger.error(f"Error in my_custom_function: {str(e)}")
        return ["⚠️ Terjadi kesalahan saat mengambil berita."]

# Timezone UTC+7
UTC_OFFSET = 7

def get_greeting():
    now = datetime.now(UTC) + timedelta(hours=UTC_OFFSET)  # Gunakan datetime.now(UTC)
    hour = now.hour

    if 5 <= hour < 12:
        return "🌞 Selamat pagi"  # Emotikon pagi
    elif 12 <= hour < 15:
        return "🌤️ Selamat siang"  # Emotikon siang
    elif 15 <= hour < 18:
        return "🌥️ Selamat sore"  # Emotikon sore
    else:
        return "🌙 Selamat malam"  # Emotikon malam

def get_market_summary():
    url = "https://indodax.com/api/summaries"
    response = requests.get(url)
    data = response.json()
    return data['tickers'], data['prices_24h']

def safe_float(value):
    try:
        return float(value)
    except (ValueError, TypeError):
        return None

def calculate_percentage_change(current_price, previous_price):
    if previous_price == 0:
        return 0
    return ((current_price - previous_price) / previous_price) * 100

def calculate_market_sentiment(tickers, prices_24h):
    positive = 0
    negative = 0
    for coin, info in tickers.items():
        if 'usdt' not in coin.lower():  # Exclude pairs with USDT
            normalized_coin = coin.replace('_', '')
            if normalized_coin in prices_24h:
                current_price = safe_float(info['last'])
                price_24h_ago = safe_float(prices_24h[normalized_coin])
                if current_price is not None and price_24h_ago is not None and price_24h_ago != 0:
                    change = calculate_percentage_change(current_price, price_24h_ago)
                    if change > 0:
                        positive += 1
                    else:
                        negative += 1
    return positive, negative

def get_top_gainers(tickers, prices_24h):
    gainers = []
    for coin, info in tickers.items():
        if 'usdt' not in coin.lower():  # Exclude pairs with USDT
            normalized_coin = coin.replace('_', '')
            if normalized_coin in prices_24h:
                current_price = safe_float(info['last'])
                price_24h_ago = safe_float(prices_24h[normalized_coin])
                if current_price is not None and price_24h_ago is not None and price_24h_ago != 0:
                    change = calculate_percentage_change(current_price, price_24h_ago)
                    if current_price > 15:  # Filter for prices above 15 IDR
                        gainers.append((coin, change))
    
    # Sort by percentage change (descending)
    gainers.sort(key=lambda x: x[1], reverse=True)
    return gainers[:3]  # Return top 3 gainers

def get_top_losers(tickers, prices_24h):
    losers = []
    for coin, info in tickers.items():
        if 'usdt' not in coin.lower():  # Exclude pairs with USDT
            normalized_coin = coin.replace('_', '')
            if normalized_coin in prices_24h:
                current_price = safe_float(info['last'])
                price_24h_ago = safe_float(prices_24h[normalized_coin])
                if current_price is not None and price_24h_ago is not None and price_24h_ago != 0:
                    change = calculate_percentage_change(current_price, price_24h_ago)
                    if current_price > 15:  # Filter for prices above 15 IDR
                        losers.append((coin, change))
    
    # Sort by percentage change (ascending)
    losers.sort(key=lambda x: x[1])
    return losers[:3]  # Return top 3 losers

def get_top_volume(tickers):
    volumes = []
    for coin, info in tickers.items():
        # Handle empty or invalid vol_idr
        vol_idr = info.get('vol_idr', '0')  # Default to '0' if vol_idr is missing or empty
        try:
            volume_idr = float(vol_idr) if vol_idr else 0  # Convert to float, or 0 if empty
        except ValueError:
            volume_idr = 0  # Fallback to 0 if conversion fails
        volumes.append((coin, volume_idr))
    
    # Sort by volume (descending)
    volumes.sort(key=lambda x: x[1], reverse=True)
    return volumes[:3]  # Return top 3 volume

def format_coin_name(coin):
    # Ubah format nama kripto dari btc_idr menjadi BTC/IDR
    return coin.replace('_', '/').upper()

async def generate_message():
    tickers, prices_24h = get_market_summary()
    btc_info = tickers['btc_idr']
    btc_current_price = safe_float(btc_info['last'])
    btc_previous_price = safe_float(prices_24h['btcidr'])
    btc_change = calculate_percentage_change(btc_current_price, btc_previous_price)

    top_gainers = get_top_gainers(tickers, prices_24h)
    top_losers = get_top_losers(tickers, prices_24h)
    top_volumes = get_top_volume(tickers)

    # Hitung market sentiment
    positive, negative = calculate_market_sentiment(tickers, prices_24h)
    market_sentiment = "cerah 🌞🌤️" if positive > negative else "suram 💀📉"

    greeting = get_greeting()

    # Format top volume message
    top_volume_message = "\n".join([f"📊 <b>{format_coin_name(coin)}</b>: [Rp. {vol:,.0f}]" for coin, vol in top_volumes])

    # Format top gainers message (dengan harga)
    top_gainers_message = "\n".join(
        [f"🚀 <b>{format_coin_name(coin)}</b>: [Rp. {safe_float(tickers[coin]['last']):,.0f}] [+{change:.2f}%]" 
         for coin, change in top_gainers]
    )

    # Format top losers message (dengan harga)
    top_losers_message = "\n".join(
        [f"💀 <b>{format_coin_name(coin)}</b>: [Rp. {safe_float(tickers[coin]['last']):,.0f}] [{change:.2f}%]" 
         for coin, change in top_losers]
    )

    # Get top 1 loser and top 1 gainer
    top_1_loser = top_losers[0] if top_losers else (None, 0)
    top_1_gainer = top_gainers[0] if top_gainers else (None, 0)

    # Pesan dinamis untuk BTC (dengan tanda + atau -)
    btc_message = (
        f"🔥  <b>BTC/IDR</b> saat ini di [Rp. {btc_current_price:,.0f}] – kemarin sempat [Rp. {btc_previous_price:,.0f}], "
        f"berarti naik [+{btc_change:.2f}%] 🥳, – Bull market beybeihhh 🕺🤑"
        if btc_change >= 0
        else f"⚠️  <b>BTC/IDR</b> saat ini di [Rp. {btc_current_price:,.0f}] – kemarin sempat [Rp. {btc_previous_price:,.0f}], "
             f"berarti turun [{btc_change:.2f}%] 💀, – Hati-hati, market lagi ga stabil kayaknya nih! 🚨📉"
    )

    # Pesan untuk Top 1 Gainer (dengan harga)
    top_gainer_message = (
        f"🏆 <b>Top 1 gainer</b> sekarang dipimpin oleh <b>{format_coin_name(top_1_gainer[0])}</b> "
        f"dengan harga [Rp. {safe_float(tickers[top_1_gainer[0]]['last']):,.0f}] dan kenaikan [+{top_1_gainer[1]:.2f}%]! "
        f"Siap-siap FOMO atau udah take profit? 😏🚀"
    )

    # Pesan untuk Top 1 Loser (dengan harga)
    top_loser_message = (
        f"💀 Disisi lain kripto yang apes hari ini ada <b>{format_coin_name(top_1_loser[0])}</b> "
        f"dengan harga [Rp. {safe_float(tickers[top_1_loser[0]]['last']):,.0f}] dan penurunan ({top_1_loser[1]:.2f}%). "
        f"Sehat-sehat ya yang lagi nge-hold <b>{format_coin_name(top_1_loser[0])}</b>. 💀⚰️"
    )

    # Bagian 1: Header, BTC, Top 1 Gainer, Top 1 Loser, Market Sentiment
    part1 = f"""
<b>====== Xyrabot News ======</b>

{greeting} Petarunks! Xyra udah siap ngasih update market buat kalian! 🚀✨

{btc_message}

{top_gainer_message}

{top_loser_message}

📊 <b>Market Sentiment:</b> Hari ini market terlihat {market_sentiment} ({positive} kripto yang naik vs {negative} kripto yang turun).
"""

    # Bagian 2: Altcoin update dan Top Volume
    part2 = f"""
📊 <b>Altcoin update:</b>
Altcoin mulai unjuk gigi! Ada yang nge-pump, ada juga yang kehilangan arah. Cek nih top altcoin hari ini? 🔥👇

<b>ETH/IDR:</b> [Rp. {safe_float(tickers['eth_idr']['last']):,.0f}] [{calculate_percentage_change(safe_float(tickers['eth_idr']['last']), safe_float(prices_24h['ethidr'])):.2f}%]
<b>BNB/IDR:</b> [Rp. {safe_float(tickers['bnb_idr']['last']):,.0f}] [{calculate_percentage_change(safe_float(tickers['bnb_idr']['last']), safe_float(prices_24h['bnbidr'])):.2f}%]
<b>SOL/IDR:</b> [Rp. {safe_float(tickers['sol_idr']['last']):,.0f}] [{calculate_percentage_change(safe_float(tickers['sol_idr']['last']), safe_float(prices_24h['solidr'])):.2f}%]

💰 <b>Top Volume:</b>
Cek nih ges siapa yang paling banyak ditransaksikan? 📊👇

{top_volume_message}
"""

    # Bagian 3: Top 3 Gainers dan Top 3 Losers
    part3 = f"""
🚀 <b>Top 3 Gainers:</b>
Yang hijau-hijau hari ini siapa aja? Ini dia yang bikin senyum para holder! 🤑💰

{top_gainers_message}

💀 <b>Top 3 Losers:</b>
Yang merah-merah hari ini siapa aja? Sabar ya buat yang masih hold! 💀👇

{top_losers_message}
"""

    # Bagian 4: News Update dan penutup
    # Mengambil 5 berita terbaru dari fungsi my_custom_function
    bot_token = config["bot_token"]
    chat_id = config["chat_id"]
    news_messages = await my_custom_function(bot_token, chat_id)

    # Mengambil 5 berita pertama dari list
    top_5_news = news_messages[:5]

    # Format pesan untuk 5 berita
    news_update_message = "\n\n".join(top_5_news)

    part4 = f"""
Ada update terbaru dari dunia kripto! Simak berita panazz ini 🔥👇

📰 <b>Berita Panazz 🥵:</b>
{news_update_message}

Gimana strategi kalian hari ini? HODL santai, nge-scalping gaspol, atau wait and see? 🤔, atau mungkin debus sebubuknya? 💀

Tetap cuan & jangan lupa DYOR! ⚡

Dan semangat buat kalian para Petarunk 💪

~Xyra🤖

<b>==== End Of Xyrabot News ====</b>
"""

    return [part1, part2, part3, part4]

def send_message():
    messages = generate_message()
    for message in messages:
        print(message)
        time.sleep(10)  # Delay 3 detik antara setiap bagian pesan

async def send_market_summary(update: Update, context: CallbackContext):
    message = generate_message()
    await update.message.reply_text(message)

async def send_scheduled_message():
    messages = await generate_message()
    bot_token = config["bot_token"]
    chat_id = config["chat_id"]
    for message in messages:
        await send_telegram_message(message, bot_token, chat_id)
        await asyncio.sleep(10)  # Delay 10 detik antara setiap bagian pesan

async def scheduled_task():
    while True:
        now = datetime.now(UTC) + timedelta(hours=UTC_OFFSET)
        if now.hour == 7 and now.minute == 0:  # 07:00 UTC+7
            await send_scheduled_message()
        elif now.hour == 12 and now.minute == 0:  # 12:00 UTC+7
            await send_scheduled_message()
        elif now.hour == 16 and now.minute == 0:  # 16:00 UTC+7
            await send_scheduled_message()
        elif now.hour == 20 and now.minute == 0:  # 20:00 UTC+7
            await send_scheduled_message()
        await asyncio.sleep(60)  # Cek setiap 60 detik

async def check_maintenance(bot_token, chat_id, maintenance_coins):
    """Asynchronous maintenance check with duration tracking."""
    global is_paused
    url = "https://indodax.com/api/pairs"
    previous_maintenance_coins = set(maintenance_coins)  # Initialize with current maintenance coins
    maintenance_start_times = {}  # Dictionary to track start times of maintenance

    while True:
        if is_paused:
            await asyncio.sleep(1)
            continue

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()

                        # Get current maintenance coins
                        current_maintenance_coins = set(
                            coin["symbol"] for coin in data if coin.get("is_maintenance") == 1
                        )

                        # Check for changes in maintenance status
                        if current_maintenance_coins != previous_maintenance_coins:
                            # Coins that started maintenance
                            new_maintenance_coins = current_maintenance_coins - previous_maintenance_coins
                            for coin in new_maintenance_coins:
                                await send_maintenance_alert(bot_token, chat_id, coin, 'start')
                                maintenance_coins.add(coin)
                                maintenance_start_times[coin] = datetime.now()  # Record start time

                            # Coins that finished maintenance
                            finished_maintenance_coins = previous_maintenance_coins - current_maintenance_coins
                            for coin in finished_maintenance_coins:
                                if coin in maintenance_start_times:
                                    start_time = maintenance_start_times[coin]
                                    duration = datetime.now() - start_time  # Calculate duration
                                    await send_maintenance_alert(bot_token, chat_id, coin, 'end', duration)
                                    maintenance_coins.discard(coin)
                                    del maintenance_start_times[coin]  # Remove from tracking

                            # Update previous maintenance state
                            previous_maintenance_coins = current_maintenance_coins
                    else:
                        logger.error(f"Failed to fetch maintenance data. Status code: {response.status}")

        except Exception as e:
            logger.error(f"Error in maintenance check: {str(e)}")

        await asyncio.sleep(30)

async def send_maintenance_alert(bot_token, chat_id, coin, status, duration=None):
    """Send maintenance alert to Telegram with optional duration."""
    global total_notifications_sent
    try:
        formatted_coin = format_pair(coin)
        if status == 'start':
            message = (
                f"⚠️ <b>WALLET ALERT</b> ⚠️\n\n"
                f"<b>{formatted_coin}</b> Sedang maintenance"
            )
        elif status == 'end':
            if duration:
                # Format duration into hours, minutes, and seconds
                hours, remainder = divmod(duration.seconds, 3600)
                minutes, seconds = divmod(remainder, 60)
                duration_str = f"{hours:02}:{minutes:02}:{seconds:02}"
                message = (
                    f"✅ <b>WALLET UPDATE</b> ✅\n\n"
                    f"<b>{formatted_coin}</b> Selesai maintenance\n"
                    f"⏱️ Durasi maintenance: <b>{duration_str}</b>"
                )
            else:
                message = (
                    f"✅ <b>WALLET UPDATE</b> ✅\n\n"
                    f"<b>{formatted_coin}</b> Selesai maintenance"
                )
        
        bot = Bot(token=bot_token)
        await bot.send_message(chat_id=chat_id, text=message, parse_mode="HTML")
        total_notifications_sent += 1
        logger.info(f"Maintenance Alert: {message}")
    except Exception as e:
        logger.error(f"Error sending maintenance message: {str(e)}")
        global error_count
        error_count += 1

def get_wallet_status(pair, maintenance_coins):
    """Get wallet status for a specific pair considering maintenance coins."""
    # Convert pair to different formats to match maintenance tracking
    maintenance_pair_checks = [
        pair,  # Original pair
        pair.replace('_', ''),  # Without underscore
        pair.replace('idr', '/IDR').upper(),  # Formatted pair
        pair.replace('_idr', '/IDR').upper(),  # Another potential format
        pair.upper().replace('_', ''),  # Uppercase without underscore
    ]
    
    # Check if any of these pair representations are in maintenance
    for check_pair in maintenance_pair_checks:
        if check_pair in maintenance_coins:
            return "⚠️ Perhatian ⚠️\n🔴 Wallet sedang maintenance 🔴"
    
    return "🟢 Wallet status: Open ✅"

async def calculate_current_rankings(current_data, prices_24h):
    """Calculate current rankings based on top gainers."""
    rankings = []
    
    # Calculate price changes for all pairs
    for pair, data in current_data.items():
        if 'usdt' in pair.lower():
            continue
        
        current_price = safe_float(data.get('last', None))
        price_24h_ago = safe_float(prices_24h.get(pair.replace('_', ''), None))
        
        # Filter out pairs with price below 25 IDR
        if current_price and current_price < 25:
            continue
        
        if current_price and price_24h_ago and price_24h_ago != 0:
            price_change_percent = ((current_price - price_24h_ago) / price_24h_ago) * 100
            rankings.append((pair, price_change_percent))
    
    # Sort by percentage change (descending)
    rankings.sort(key=lambda x: x[1], reverse=True)
    
    # Create dictionaries for rankings
    rank_dict = {}
    reverse_rank_dict = {}
    
    # Calculate normal rankings (from top, for gainers)
    for idx, (pair, change) in enumerate(rankings):
        rank_dict[pair] = idx + 1  # Start counting from 1
        
    # Calculate reverse rankings (from bottom, for losers)
    for idx, (pair, change) in enumerate(reversed(rankings)):
        reverse_rank_dict[pair] = idx + 1  # Start counting from 1
    
    return rank_dict, reverse_rank_dict, rankings

def get_rank_display(rank, reverse_rank, price_change_percent):
    """Return formatted rank display based on position."""
    if rank <= 10:
        return f"🔥 Top #{rank}"
    elif reverse_rank <= 10:
        return f"💀 Low #{reverse_rank}"
    else:
        return f"📊 Rank #{rank}"

class MonitorState:
    def __init__(self, initial_prices, initial_volumes, initial_times):
        self.previous_prices = initial_prices.copy()
        self.previous_volumes = initial_volumes.copy()
        self.previous_times = initial_times.copy()

async def monitor_price_change(bot_token, chat_id, initial_prices, initial_volumes, initial_times, maintenance_coins, threshold_percent=5, threshold_price_idr=25, threshold_volume_change=500_000_000, interval=30, volume_threshold=300_000_000):
    global is_paused
    logger.info("Bot is running... Monitoring Price changes...")

    # State terpisah untuk price monitor
    price_state = MonitorState(initial_prices, initial_volumes, initial_times)
    first_run = True

    while True:
        if is_paused:
            logger.info("Bot is paused. Sleeping for 1 second.")
            await asyncio.sleep(1)
            continue

        await api_limiter()
        current_data = await get_all_crypto_data()
        if current_data is None:
            continue

        prices_24h = await get_summary_data()
        if prices_24h is None:
            continue
        prices_24h = prices_24h['prices_24h']

        rank_dict, reverse_rank_dict, rankings = await calculate_current_rankings(current_data, prices_24h)
        current_time = datetime.now()

        for pair, data in current_data.items():
            if 'usdt' in pair.lower():
                continue

            current_price = safe_float(data.get('last', None))
            current_volume = safe_float(data.get('vol_idr', None))

            if current_price is None or current_volume is None:
                continue

            previous_price = price_state.previous_prices.get(pair)
            previous_volume = price_state.previous_volumes.get(pair)
            previous_time = price_state.previous_times.get(pair)

            if previous_price is None or previous_volume is None or previous_time is None:
                price_state.previous_prices[pair] = current_price
                price_state.previous_volumes[pair] = current_volume
                price_state.previous_times[pair] = current_time
                continue

            logger.info(f"Pair: {pair}")
            logger.info(f"Previous Price: {previous_price}, Current Price: {current_price}")
            logger.info(f"Previous Volume: {previous_volume}, Current Volume: {current_volume}")
            logger.info(f"Previous Time: {previous_time}, Current Time: {current_time}")

            if previous_price != 0:
                price_change_percent = ((current_price - previous_price) / previous_price) * 100
            else:
                price_change_percent = 0

            volume_change = current_volume - previous_volume

            if volume_change > 0:
                volume_change_text = f"🟢Volume meningkat: Rp.{volume_change:,.0f}\n"
            else:
                volume_change_text = f"🔴Volume menurun: Rp.{abs(volume_change):,.0f}\n"

            time_diff = current_time - previous_time

            logger.info(f"Price Change Percent: {price_change_percent:.2f}%, Volume Change: {volume_change:.2f}")

            price_criteria_met = abs(price_change_percent) >= threshold_percent
            volume_criteria_met = abs(volume_change) >= threshold_volume_change
            high_price_criteria_met = current_price >= threshold_price_idr

            criteria_met = not first_run and (price_criteria_met and volume_criteria_met and high_price_criteria_met)

            if criteria_met:
                logger.info(f"Criteria met for {pair}: price_change_percent={price_change_percent:.2f}%, volume_change={volume_change:.2f}")

                wallet_status = get_wallet_status(pair, maintenance_coins)

                if price_change_percent > 0:
                    price_change_symbol = "🚀"
                    change_direction = "Naik"
                else:
                    price_change_symbol = "🔻"
                    change_direction = "Turun"

                pair_base = pair.replace('idr', '').replace('_', '').upper()
                pair_with_idr = f"{pair_base}/IDR"

                # Get current rank and reverse rank
                current_rank = rank_dict.get(pair, len(rankings))
                current_reverse_rank = reverse_rank_dict.get(pair, 1)
                rank_display = get_rank_display(current_rank, current_reverse_rank, price_change_percent)

                formatted_time_diff = str(time_diff).split('.')[0]

                # Update message formatting
                if wallet_status == "⚠️ Perhatian ⚠️\n🔴 Wallet sedang maintenance 🔴":
                    message = (f"<b>{price_change_symbol} {pair_with_idr} ({price_change_percent:.2f}%)</b> <b>{rank_display}</b>\n"
                               f"Harga : Rp.{current_price:,.0f}\n"
                               f"Harga sebelumnya : Rp.{previous_price:,.0f}\n"
                               f"Volume : Rp.{current_volume:,.0f}\n"
                               f"{volume_change_text}"
                               f"<b>{change_direction} dalam waktu : {formatted_time_diff}</b>\n"
                               f"<b>{wallet_status}</b>")
                else:
                    message = (f"<b>{price_change_symbol} {pair_with_idr} ({price_change_percent:.2f}%)</b> <b>{rank_display}</b>\n"
                               f"Harga : Rp.{current_price:,.0f}\n"
                               f"Harga sebelumnya : Rp.{previous_price:,.0f}\n"
                               f"Volume : Rp.{current_volume:,.0f}\n"
                               f"{volume_change_text}"
                               f"<b>{change_direction} dalam waktu : {formatted_time_diff}</b>\n")

                await send_telegram_message(message, bot_token, chat_id)

                pair_notifications[pair_with_idr] += 1

                
                price_state.previous_prices[pair] = current_price
                price_state.previous_volumes[pair] = current_volume
                price_state.previous_times[pair] = current_time

        first_run = False
        await asyncio.sleep(interval)

async def monitor_pump_dump_alerts(bot_token, chat_id, initial_prices, initial_volumes, initial_times, maintenance_coins, pump_dump_threshold=20, volume_change_threshold=10_000_000, interval=5, threshold_price_idr=25):
    global is_paused
    logger.info("Monitoring for Pump/Dump and Volume changes...")

    # State terpisah untuk pump/dump monitor
    pump_state = MonitorState(initial_prices, initial_volumes, initial_times)
    first_run = True

    while True:
        if is_paused:
            await asyncio.sleep(1)
            continue

        await api_limiter()
        current_data = await get_all_crypto_data()
        if current_data is None:
            continue

        prices_24h = await get_summary_data()
        if prices_24h is None:
            continue
        prices_24h = prices_24h['prices_24h']

        rank_dict, reverse_rank_dict, rankings = await calculate_current_rankings(current_data, prices_24h)
        current_time = datetime.now()

        for pair, data in current_data.items():
            if 'usdt' in pair.lower():
                continue

            current_price = safe_float(data.get('last', None))
            current_volume = safe_float(data.get('vol_idr', None))

            if current_price is None or current_volume is None:
                continue

            previous_price = pump_state.previous_prices.get(pair)
            previous_volume = pump_state.previous_volumes.get(pair)
            previous_time = pump_state.previous_times.get(pair)

            if previous_price is None or previous_volume is None or previous_time is None:
                pump_state.previous_prices[pair] = current_price
                pump_state.previous_volumes[pair] = current_volume
                pump_state.previous_times[pair] = current_time
                continue

            time_diff = current_time - previous_time

            # Calculate price and volume changes
            if previous_price != 0:
                price_change_percent = ((current_price - previous_price) / previous_price) * 100
            else:
                price_change_percent = 0

            volume_change = current_volume - previous_volume

            if volume_change > 0:
                volume_change_text = f"🟢Volume meningkat: Rp.{volume_change:,.0f}\n"
            else:
                volume_change_text = f"🔴Volume menurun: Rp.{abs(volume_change):,.0f}\n"

            logger.info(f"Pair: {pair}, Price Change: {price_change_percent:.2f}%, Volume Change: {volume_change:.2f} IDR")

            # Check if conditions for pump/dump or volume spike are met
            price_criteria_met = abs(price_change_percent) >= pump_dump_threshold
            volume_criteria_met = abs(volume_change) >= volume_change_threshold
            high_price_criteria_met = current_price >= threshold_price_idr
            
            if price_criteria_met and volume_criteria_met and high_price_criteria_met:
                logger.info(f"Pump/Dump Alert for {pair}: price_change_percent={price_change_percent:.2f}%, volume_change={volume_change:.2f} IDR")

                wallet_status = get_wallet_status(pair, maintenance_coins)

                if price_change_percent > 0:
                    price_change_symbol = "🚀"
                    change_direction = "Pump"
                    if price_change_percent > 100:
                        alert_symbol = "⚠ MEGA PUMP ALERT ⚠"
                    elif price_change_percent > 50:
                        alert_symbol = "⚠ BIG PUMP ALERT ⚠"
                    else:
                        alert_symbol = "⚠ PUMP ALERT ⚠"
                else:
                    price_change_symbol = "🔻"
                    change_direction = "Dump"
                    if abs(price_change_percent) > 100:
                        alert_symbol = "⚠ MEGA DUMP ALERT ⚠"
                    elif abs(price_change_percent) > 50:
                        alert_symbol = "⚠ BIG DUMP ALERT ⚠"
                    else:
                        alert_symbol = "⚠ DUMP ALERT ⚠"

                pair_base = pair.replace('idr', '').replace('_', '').upper()
                pair_with_idr = f"{pair_base}/IDR"

                # Get current rank and reverse rank
                current_rank = rank_dict.get(pair, len(rankings))
                current_reverse_rank = reverse_rank_dict.get(pair, 1)
                rank_display = get_rank_display(current_rank, current_reverse_rank, price_change_percent)

                hours, remainder = divmod(time_diff.seconds, 3600)
                minutes, seconds = divmod(remainder, 60)
                formatted_time_diff = f"{hours:02}:{minutes:02}:{seconds:02}"

                # Update message formatting
                if wallet_status == "⚠️ Perhatian ⚠️\n🔴 Wallet sedang maintenance 🔴":
                    message = (f"<b>{alert_symbol}</b>\n" 
                               f"<b>{price_change_symbol} {pair_with_idr} ({price_change_percent:.2f}%)</b> <b>{rank_display}</b>\n"
                               f"Harga: Rp.{current_price:,.0f}\n"
                               f"Harga sebelumnya: Rp.{previous_price:,.0f}\n"
                               f"Volume: Rp.{current_volume:,.0f}\n"
                               f"{volume_change_text}"
                               f"<b>{change_direction} dalam waktu: {formatted_time_diff}</b>\n"
                               f"<b>{wallet_status}</b>")
                else:
                    message = (f"<b>{alert_symbol}</b>\n"
                               f"<b>{price_change_symbol} {pair_with_idr} ({price_change_percent:.2f}%)</b> <b>{rank_display}</b>\n"
                               f"Harga: Rp.{current_price:,.0f}\n"
                               f"Harga sebelumnya: Rp.{previous_price:,.0f}\n"
                               f"Volume: Rp.{current_volume:,.0f}\n"
                               f"{volume_change_text}"
                               f"<b>{change_direction} dalam waktu: {formatted_time_diff}</b>\n")

                await send_telegram_message(message, bot_token, chat_id)

                
                pump_state.previous_prices[pair] = current_price
                pump_state.previous_volumes[pair] = current_volume
                pump_state.previous_times[pair] = current_time

        await asyncio.sleep(interval)

# Main function to integrate both monitors
async def main():
    global config
    try:
        config = load_config()
        if not config:
            bot_token = input("Masukkan Bot Token: ")
            chat_id = input("Masukkan Chat ID: ")
            threshold_percent = float(input("Masukkan batas persentase perubahan harga yang diinginkan: "))
            threshold_price_idr = float(input("Masukkan batas harga IDR yang diinginkan: "))
            threshold_volume_change = float(input("Masukkan batas perubahan volume yang diinginkan: "))
            interval = float(input("Masukkan waktu interval pemantauan harga (detik): "))
            volume_threshold = float(input("Masukkan batas volume yang diinginkan: "))
            
            config = {
                "bot_token": bot_token,
                "chat_id": chat_id,
                "threshold_percent": threshold_percent,
                "threshold_price_idr": threshold_price_idr,
                "threshold_volume_change": threshold_volume_change,
                "interval": interval,
                "volume_threshold": volume_threshold
            }
            save_config(config)
        else:
            bot_token = config["bot_token"]
            chat_id = config["chat_id"]
            threshold_percent = config["threshold_percent"]
            threshold_price_idr = config["threshold_price_idr"]
            threshold_volume_change = config["threshold_volume_change"]
            interval = config["interval"]
            volume_threshold = config["volume_threshold"]

        initial_data = await get_all_crypto_data()
        if initial_data is None:
            logger.error("Failed to fetch initial data. Exiting.")
            return

        current_time = datetime.now()
        initial_prices = {pair: safe_float(data.get('last', None)) for pair, data in initial_data.items()}
        initial_volumes = {pair: safe_float(data.get('vol_idr', None)) for pair, data in initial_data.items()}
        initial_times = {pair: current_time for pair in initial_data.keys()}

        signal.signal(signal.SIGINT, lambda sig, frame: signal_handler(sig, frame, bot_token, chat_id))

        await send_telegram_message("Xyrabot Is Online", bot_token, chat_id)
        await send_telegram_message("Version: 2.8 Beta", bot_token, chat_id)

        application = Application.builder().token(bot_token).build()
        application.add_handler(CommandHandler("market", send_market_summary))
        application.add_handler(CommandHandler("pause", pause))
        application.add_handler(CommandHandler("resume", resume))
        application.add_handler(CommandHandler("stats", send_stats))
        application.add_handler(CommandHandler("news", send_news))

        await application.initialize()
        await application.start()
        await application.updater.start_polling()

        asyncio.create_task(scheduled_task())  # Jalankan penjadwalan

        # Start both price monitoring and pump/dump monitoring
        price_monitor_task = asyncio.create_task(monitor_price_change(bot_token, chat_id, initial_prices, initial_volumes, initial_times, maintenance_coins, threshold_percent, threshold_price_idr, threshold_volume_change, interval, volume_threshold))
        pump_dump_monitor_task = asyncio.create_task(monitor_pump_dump_alerts(bot_token, chat_id, initial_prices, initial_volumes, initial_times, maintenance_coins, threshold_price_idr=threshold_price_idr))
        maintenance_monitor_task = asyncio.create_task(check_maintenance(bot_token, chat_id, maintenance_coins))

        await price_monitor_task
        await pump_dump_monitor_task
        await maintenance_monitor_task

        await application.running()

    except Exception as e:
        logger.error(f"An error occurred: {str(e)}")
        global error_count
        error_count += 1
        logger.info("Reconnecting the bot...")
        await send_telegram_message(f"Xyrabot Is Paused (Reason: {str(e)})", bot_token, chat_id)
        await asyncio.sleep(30)
        await main()

if __name__ == '__main__':
    asyncio.run(main())
