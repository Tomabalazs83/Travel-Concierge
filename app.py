import os
import asyncio
import logging
import random
from datetime import datetime as dt, timedelta

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

import google.generativeai as genai

from playwright.async_api import async_playwright

# ─── CONFIGURATION ───────────────────────────────────────────────────────────────
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_KEY = os.environ.get("GEMINI_KEY")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ─── AI SETUP ────────────────────────────────────────────────────────────────────
ai_brain = None
try:
    if not GEMINI_KEY:
        logger.warning("GEMINI_KEY not set → AI disabled")
    else:
        genai.configure(api_key=GEMINI_KEY)
        ai_brain = genai.GenerativeModel(
            "gemini-2.5-flash",  # Valid model name
            system_instruction=(
                "You are Jeeves, a sophisticated British butler. "
                "Always address the user as 'Sir'. "
                "Be witty, dry, concise, and elegant in your replies."
            )
        )
        logger.info("Concierge initialized with gemini-1.5-flash")
except Exception as e:
    logger.error(f"AI setup failed: {e}")

# ─── TRAVEL SEARCH TOOL (Async Skyscanner Scraper) ───────────────────────────────
async def get_travel_info(dest_entity: str) -> str:
    # Fixed dates for testing (July 1–10, 2026)
    depart = dt(2026, 7, 1)
    return_d = dt(2026, 7, 10)

    # IATA map
    iata_map = {
        "City:honolulu_hi_us": "HNL",
        "City:denpasar_id": "DPS",
        "City:london_gb": "LON"
    }
    dest_iata = iata_map.get(dest_entity, "XXX")

    try:
        result = await search_skyscanner_async("AMS", dest_iata, depart, return_d)
        return result
    except Exception as e:
        logger.error(f"Skyscanner scraper error: {e}")
        return "The details are currently elusive, Sir."

async def search_skyscanner_async(origin_iata, dest_iata, depart_date, return_date):
    # Format dates as YYMMDD
    depart_str = depart_date.strftime("%y%m%d")
    return_str = return_date.strftime("%y%m%d")

    url = f"https://www.skyscanner.net/transport/flights/{origin_iata.lower()}/{dest_iata.lower()}/{depart_str}/{return_str}/?adults=1&adultsv2=1&cabinclass=economy&children=0&childrenv2=&inboundaltsenabled=false&infants=0&outboundaltsenabled=false&preferdirects=false&ref=home&rtn=1"

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 800},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36',
            locale='en-US',
            timezone_id='Europe/Amsterdam'
        )
        page = await context.new_page()

        logger.info(f"Navigating to: {url}")
        await page.goto(url, timeout=90000)
        await page.wait_for_load_state("networkidle", timeout=90000)

        # Wait for results
        try:
            await page.wait_for_selector("div[data-testid='flight-card']", timeout=60000)
            await asyncio.sleep(random.uniform(2, 5))  # mimic human
        except Exception as e:
            await browser.close()
            return "No results found or page failed to load."

        # Extract cheapest price and details
        cards = await page.query_selector_all("div[data-testid='flight-card']")
        if not cards:
            await browser.close()
            return "No flight cards found."

        prices = []
        for card in cards:
            try:
                price_elem = await card.query_selector("span[data-testid='price']")
                airline_elem = await card.query_selector("span[data-testid='airline-name']")
                stops_elem = await card.query_selector("span[data-testid='stops']")
                duration_elem = await card.query_selector("span[data-testid='duration']")

                price = await price_elem.inner_text() if price_elem else "N/A"
                airline = await airline_elem.inner_text() if airline_elem else "N/A"
                stops = await stops_elem.inner_text() if stops_elem else "N/A"
                duration = await duration_elem.inner_text() if duration_elem else "N/A"

                prices.append({
                    "price": price.strip(),
                    "airline": airline.strip(),
                    "stops": stops.strip(),
                    "duration": duration.strip()
                })
            except:
                continue

        if prices:
            cheapest = min(prices, key=lambda x: float(x["price"].replace("€", "").replace(",", "").strip()) if x["price"] != "N/A" else float("inf"))
            result = f"💰 **{cheapest['price']}**\nAirline: {cheapest['airline']}\nStops: {cheapest['stops']}\nDuration: {cheapest['duration']}"
        else:
            result = "No readable prices found — selectors may have changed."

        await browser.close()
        return result

# ─── BOT HANDLERS ────────────────────────────────────────────────────────────────
async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if ai_brain is None:
        await update.message.reply_text("I'm dreadfully sorry, Sir, my thoughts are a bit muddled.")
        return

    user_text = update.message.text.strip()
    if not user_text:
        return

    if 'chat_session' not in context.user_data:
        context.user_data['chat_session'] = ai_brain.start_chat(history=[])
        logger.info("New chat session created")

    chat_session = context.user_data['chat_session']

    try:
        response = chat_session.send_message(user_text)
        await update.message.reply_text(response.text.strip())
    except Exception as e:
        logger.error(f"Chat error: {e}")
        await update.message.reply_text("A momentary lapse in decorum, Sir. Shall we try again?")

async def daily_brief(context: ContextTypes.DEFAULT_TYPE):
    chat_id = getattr(context.job, 'chat_id', None) or context.user_data.get('chat_id')
    if not chat_id:
        logger.warning("daily_brief called without chat_id")
        return

    options = {
        "Hawaii": "City:honolulu_hi_us",
        "Bali": "City:denpasar_id",
        "London": "City:london_gb"
    }

    await context.bot.send_message(chat_id=chat_id, text="Consulting the summer registries, Sir...")

    report = "🛎 **Travel Briefing, Sir**\n\n"
    data_for_ai = ""

    for name, entity in options.items():
        info = await get_travel_info(entity)  # Note: await for async
        report += f"✈️ **{name}**:\n{info}\n\n"
        data_for_ai += f"{name}: {info}. "

    await context.bot.send_message(chat_id=chat_id, text=report, parse_mode='Markdown')

    if ai_brain is None:
        await context.bot.send_message(chat_id=chat_id, text="The analytical department appears to be taking tea at present, Sir.")
        return

    try:
        if 'chat_session' not in context.user_data:
            context.user_data['chat_session'] = ai_brain.start_chat(history=[])
        chat_session = context.user_data['chat_session']

        analysis_res = chat_session.send_message(
            f"Provide a witty, dry, two-sentence analysis of these flight prices and details for Sir: {data_for_ai}"
        )
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"🎩 **Butler's insight:**\n{analysis_res.text.strip()}",
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Analysis error: {e}")
        await context.bot.send_message(
            chat_id=chat_id,
            text="The analytical department appears to be taking tea at present, Sir."
        )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    context.user_data['chat_id'] = chat_id

    if ai_brain and 'chat_session' not in context.user_data:
        context.user_data['chat_session'] = ai_brain.start_chat(history=[])
        logger.info(f"Persistent chat session created for user {chat_id}")

    await update.message.reply_text(
        "The Concierge is at your service, Sir. I have cleared my local ledger for our fresh start."
    )

    jobs = context.job_queue.get_jobs_by_name('daily_check')
    for job in jobs:
        job.schedule_removal()

    context.job_queue.run_daily(
        daily_brief,
        time=datetime.time(hour=8, minute=0),
        chat_id=chat_id,
        name='daily_check'
    )

async def check_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['chat_id'] = update.effective_chat.id
    await daily_brief(context)

# ─── MAIN ────────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    if not TELEGRAM_TOKEN:
        logger.critical("TELEGRAM_TOKEN missing → cannot start")
        exit(1)

    logger.info("Starting butler bot...")

    app = (
        ApplicationBuilder()
        .token(TELEGRAM_TOKEN)
        .get_updates_read_timeout(30)
        .get_updates_write_timeout(30)
        .get_updates_pool_timeout(30)
        .build()
    )

    loop = asyncio.get_event_loop()
    loop.run_until_complete(app.bot.delete_webhook(drop_pending_updates=True))
    logger.info("Webhook cleaned, pending updates dropped")

    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('check', check_now))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))

    logger.info("Bot handlers registered. Starting polling...")
    app.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
        poll_interval=1.0,
        timeout=30,
        bootstrap_retries=3
    )
