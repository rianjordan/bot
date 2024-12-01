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
        await bot.send_message(chat_id=chat_id, text=message, parse_mode="HTML")
        total_notifications_sent += 1
        logger.info("Sending Notification")
    except Exception as e:
        logger.error(f"Error sending message: {str(e)}")
        global error_count
        error_count += 1

async def get_all_crypto_data():
    api_url = 'https://indodax.com/api/tickers'
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

rate_limiter = AsyncLimiter(50, 30)  # Rate limit to 50 requests per 30 seconds

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

async def send_maintenance_alert(bot_token, chat_id, coin, status):
    """Mengirim pesan maintenance ke Telegram"""
    global total_notifications_sent
    try:
        formatted_coin = format_pair(coin)
        if status == 'start':
            message = (
                f"⚠️ <b>WALLET ALERT</b> ⚠️\n\n"
                f"<b>{formatted_coin}</b> Sedang maintenance"
            )
        elif status == 'end':
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

async def check_maintenance(bot_token, chat_id, maintenance_coins):
    """Asynchronous maintenance check"""
    global is_paused
    url = "https://indodax.com/api/pairs"
    previous_maintenance_coins = set()

    while True:
        if is_paused:
            await asyncio.sleep(1)
            continue

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()

                        current_maintenance_coins = set()
                        for coin in data:
                            if coin.get("is_maintenance") == 1:
                                current_maintenance_coins.add(coin["symbol"])

                        # New maintenance coins
                        new_maintenance_coins = current_maintenance_coins - previous_maintenance_coins
                        if new_maintenance_coins:
                            for coin in new_maintenance_coins:
                                await send_maintenance_alert(bot_token, chat_id, coin, 'start')
                                maintenance_coins.add(coin)

                        # Coins finished maintenance
                        finished_maintenance_coins = previous_maintenance_coins - current_maintenance_coins
                        if finished_maintenance_coins:
                            for coin in finished_maintenance_coins:
                                await send_maintenance_alert(bot_token, chat_id, coin, 'end')
                                maintenance_coins.discard(coin)

                        previous_maintenance_coins = current_maintenance_coins
                    else:
                        logger.error(f"Failed to fetch maintenance data. Status code: {response.status}")

        except Exception as e:
            logger.error(f"Error in maintenance check: {str(e)}")

        await asyncio.sleep(15)

async def get_wallet_status(pair):
    """Mendapatkan status wallet untuk pasangan tertentu."""
    if pair in maintenance_coins:
        return "🔴 Wallet status: Maintenance ⚠️"
    else:
        return "🟢 Wallet status: Open ✅"

async def monitor_price_change(bot_token, chat_id, initial_prices, initial_volumes, initial_times, threshold_percent=5, threshold_price_idr=25, threshold_volume_change=500_000_000, interval=30, volume_threshold=300_000_000):
    global is_paused
    logger.info("Bot is running... Monitoring Price changes...")

    previous_prices = initial_prices.copy()
    previous_volumes = initial_volumes.copy()
    previous_times = initial_times.copy()
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

        current_time = datetime.now()

        for pair, data in current_data.items():
            if 'usdt' in pair.lower():
                continue

            current_price = safe_float(data.get('last', None))
            current_volume = safe_float(data.get('vol_idr', None))

            if current_price is None or current_volume is None:
                continue

            previous_price = previous_prices.get(pair)
            previous_volume = previous_volumes.get(pair)
            previous_time = previous_times.get(pair)

            if previous_price is None or previous_volume is None or previous_time is None:
                previous_prices[pair] = current_price
                previous_volumes[pair] = current_volume
                previous_times[pair] = current_time
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

            time_diff = current_time - previous_time

            logger.info(f"Price Change Percent: {price_change_percent:.2f}%, Volume Change: {volume_change:.2f}")

            price_criteria_met = abs(price_change_percent) >= threshold_percent
            volume_criteria_met = abs(volume_change) >= threshold_volume_change
            high_price_criteria_met = current_price >= threshold_price_idr

            criteria_met = not first_run and (price_criteria_met and volume_criteria_met and high_price_criteria_met)

            if criteria_met:
                logger.info(f"Criteria met for {pair}: price_change_percent={price_change_percent:.2f}%, volume_change={volume_change:.2f}")

                wallet_status = await get_wallet_status(pair)

                if price_change_percent > 0:
                    price_change_symbol = "🚀"
                    change_direction = "Naik"
                else:
                    price_change_symbol = "🔻"
                    change_direction = "Turun"

                pair_base = pair.replace('idr', '').replace('_', '').upper()
                pair_with_idr = f"{pair_base}/IDR"

                formatted_time_diff = str(time_diff).split('.')[0]

                message = (f"{price_change_symbol} {pair_with_idr} ({price_change_percent:.2f}%)\n"
                           f"Harga : Rp.{current_price:,.0f}\n"
                           f"Harga sebelumnya : Rp.{previous_price:,.0f}\n"
                           f"Volume : Rp.{current_volume:,.0f}\n"
                           f"(Volume trades : Rp.{volume_change:,.0f})\n"
                           f"{change_direction} dalam kurun waktu : {formatted_time_diff}"
                           f"{wallet_status}")

                await send_telegram_message(message, bot_token, chat_id)

                pair_notifications[pair_with_idr] += 1

                previous_prices[pair] = current_price
                previous_volumes[pair] = current_volume
                previous_times[pair] = current_time

        first_run = False
        await asyncio.sleep(interval)

# New Pump/Dump Monitoring Logic
async def monitor_pump_dump_alerts(bot_token, chat_id, initial_prices, initial_volumes, initial_times, pump_dump_threshold=20, volume_change_threshold=10_000_000, alert_window_minutes=240, interval=10, threshold_price_idr=25):
    global is_paused
    logger.info("Monitoring for Pump/Dump and Volume changes...")

    previous_prices = initial_prices.copy()
    previous_volumes = initial_volumes.copy()
    previous_times = initial_times.copy()
    first_run = True

    reset_timer = 0  # new variable to keep track of the reset timer

    while True:
        if is_paused:
            await asyncio.sleep(1)
            continue

        await api_limiter()
        current_data = await get_all_crypto_data()
        if current_data is None:
            continue

        current_time = datetime.now()

        for pair, data in current_data.items():
            if 'usdt' in pair.lower():
                continue

            current_price = safe_float(data.get('last', None))
            current_volume = safe_float(data.get('vol_idr', None))

            if current_price is None or current_volume is None:
                continue

            previous_price = previous_prices.get(pair)
            previous_volume = previous_volumes.get(pair)
            previous_time = previous_times.get(pair)

            if previous_price is None or previous_volume is None or previous_time is None:
                previous_prices[pair] = current_price
                previous_volumes[pair] = current_volume
                previous_times[pair] = current_time
                continue

            time_diff = current_time - previous_time

            # Calculate price and volume changes
            if previous_price != 0:
                price_change_percent = ((current_price - previous_price) / previous_price) * 100
            else:
                price_change_percent = 0

            volume_change = current_volume - previous_volume

            logger.info(f"Pair: {pair}, Price Change: {price_change_percent:.2f}%, Volume Change: {volume_change:.2f} IDR")

            # Check if conditions for pump/dump or volume spike are met
            price_criteria_met = abs(price_change_percent) >= pump_dump_threshold
            volume_criteria_met = abs(volume_change) >= volume_change_threshold
            high_price_criteria_met = current_price >= threshold_price_idr
            time_criteria_met = True
            
            if price_criteria_met and volume_criteria_met and high_price_criteria_met:
                logger.info(f"Pump/Dump Alert for {pair}: price_change_percent={price_change_percent:.2f}%, volume_change={volume_change:.2f} IDR")

                wallet_status = await get_wallet_status(pair)

                if price_change_percent > 0:
                    price_change_symbol = "🚀"
                    change_direction = "PUMP"
                    if price_change_percent > 100:
                        alert_symbol = "⚠ MEGA PUMP ALERT ⚠"
                    elif price_change_percent > 50:
                        alert_symbol = "⚠ BIG PUMP ALERT ⚠"
                    else:
                        alert_symbol = "⚠ PUMP ALERT ⚠"
                else:
                    price_change_symbol = "🔻"
                    change_direction = "DUMP"
                    if abs(price_change_percent) > 100:
                        alert_symbol = "⚠ MEGA DUMP ALERT ⚠"
                    elif abs(price_change_percent) > 50:
                        alert_symbol = "⚠ BIG DUMP ALERT ⚠"
                    else:
                        alert_symbol = "⚠ DUMP ALERT ⚠"

                pair_base = pair.replace('idr', '').replace('_', '').upper()
                pair_with_idr = f"{pair_base}/IDR"

                hours, remainder = divmod(time_diff.seconds, 3600)
                minutes, seconds = divmod(remainder, 60)
                formatted_time_diff = f"{hours:02}:{minutes:02}:{seconds:02}"

                message = (f"{alert_symbol}\n"
                           f"{price_change_symbol} {pair_with_idr} ({price_change_percent:.2f}%)\n"
                           f"Harga: Rp.{current_price:,.0f}\n"
                           f"Harga sebelumnya: Rp.{previous_price:,.0f}\n"
                           f"Volume: Rp.{current_volume:,.0f}\n"
                           f"(Volume Trades: Rp.{volume_change:,.0f})\n"
                           f"{change_direction} dalam waktu: {formatted_time_diff}"
                           f"{wallet_status}")

                await send_telegram_message(message, bot_token, chat_id)

                previous_prices[pair] = current_price
                previous_volumes[pair] = current_volume
                previous_times[pair] = current_time

        # Reset previous values every 30 minutes
        reset_timer += interval
        if reset_timer >= alert_window_minutes * 60:
            reset_timer = 0
            previous_prices = initial_prices.copy()
            previous_volumes = initial_volumes.copy()
            previous_times = initial_times.copy()
            logger.info("Resetting previous values...")

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

        application = Application.builder().token(bot_token).build()
        application.add_handler(CommandHandler("market", send_market_summary))
        application.add_handler(CommandHandler("pause", pause))
        application.add_handler(CommandHandler("resume", resume))
        application.add_handler(CommandHandler("stats", send_stats))

        await application.initialize()
        await application.start()
        await application.updater.start_polling()

        # Start both price monitoring and pump/dump monitoring
        price_monitor_task = asyncio.create_task(monitor_price_change(bot_token, chat_id, initial_prices, initial_volumes, initial_times, threshold_percent, threshold_price_idr, threshold_volume_change, interval, volume_threshold))
        pump_dump_monitor_task = asyncio.create_task(monitor_pump_dump_alerts(bot_token, chat_id, initial_prices, initial_volumes, initial_times, threshold_price_idr=threshold_price_idr))
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
