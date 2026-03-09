import os
import http.client
import json
import datetime
import logging
import asyncio
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

# ─── CONFIGURATION ───────────────────────────────────────────────────────────────
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_KEY = os.environ.get("GEMINI_KEY")
RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY")

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
            "gemini-2.5-flash-lite",
            system_instruction=(
                "You are Jeeves, a sophisticated British butler. "
                "Always address the user as 'Sir'. "
                "Be witty, dry, concise, and elegant in your replies."
            )
        )
        logger.info("Concierge initialized with gemini-2.5-flash-lite")
except Exception as e:
    logger.error(f"AI setup failed: {e}")

# ─── TRAVEL SEARCH TOOL (Booking.com API) ────────────────────────────────────────
def get_travel_info(dest_entity: str) -> str:
    # Fixed specific dates (July 1–10, 2026)
    out_date = "2026-07-01"   # arrival / check-in
    ret_date = "2026-07-10"   # departure / check-out

    # City name for destination search
    city_map = {
        "City:honolulu_hi_us": "Honolulu",
        "City:denpasar_id": "Denpasar",
        "City:london_gb": "London"
    }
    city_name = city_map.get(dest_entity, "Unknown")

    conn = http.client.HTTPSConnection("booking-com15.p.rapidapi.com")
    headers = {
        'x-rapidapi-key': RAPIDAPI_KEY,
        'x-rapidapi-host': "booking-com15.p.rapidapi.com"
    }

    flight_info = "Flights currently elusive, Sir. (Limited support in this API)"
    hotel_info = ""

    # 1. Search Destination to get dest_id
    try:
        dest_path = f"/api/v1/hotels/searchDestination?query={city_name}&languagecode=en-us&search_type=CITY&arrival_date={out_date}&departure_date={ret_date}"
        conn.request("GET", dest_path, headers=headers)
        res = conn.getresponse()
        data = res.read()
        response_text = data.decode('utf-8')
        logger.info(f"Booking.com Destination Search status for {city_name}: {res.status}")
        logger.info(f"Destination preview: {response_text[:500]}...")

        dest_id = ""
        if res.status == 200:
            dest_json = json.loads(response_text)
            if dest_json.get("status") is True:
                dest_results = dest_json.get("data", []) or dest_json.get("results", []) or []
                if dest_results:
                    dest_id = dest_results[0].get("dest_id", "") or dest_results[0].get("id", "")
                    logger.info(f"Found dest_id: {dest_id}")
            else:
                logger.warning(f"Destination search failed: {dest_json.get('message')}")
    except Exception as e:
        logger.error(f"Destination search error: {e}")
        dest_id = ""

    # 2. Search 4+ star hotels using dest_id
    try:
        if dest_id:
            checkin = out_date
            checkout = ret_date
            hotel_path = f"/api/v1/hotels/searchHotels?dest_id={dest_id}&checkin={checkin}&checkout={checkout}&adults=1&room_number=1&currency_code=EUR&filter_by_stars=4,5&sort=price_asc"
            conn.request("GET", hotel_path, headers=headers)
            res = conn.getresponse()
            data = res.read()
            response_text = data.decode('utf-8')
            logger.info(f"Booking.com Hotels API status for {city_name}: {res.status}")
            logger.info(f"Hotels preview: {response_text[:500]}...")

            if res.status == 200:
                hotel_json = json.loads(response_text)
                if hotel_json.get("status") is True:
                    hotels = hotel_json.get("hotels", []) or hotel_json.get("results", []) or []
                    if hotels:
                        cheapest = min(hotels, key=lambda h: h.get("price", float("inf")))
                        name = cheapest.get("name", "Unknown Hotel")
                        address = cheapest.get("address", "Address not provided")
                        price = f"€{cheapest.get('price', '—')} for stay"
                        hotel_info = f"🏨 **Recommended hotel:** {name}\n   {address}\n   {price}"
                    else:
                        hotel_info = "No 4+ star hotels found in response."
                else:
                    hotel_info = f"Hotel search failed: {hotel_json.get('message')}"
            else:
                hotel_info = f"Hotel API error ({res.status}): {response_text[:200]}..."
        else:
            hotel_info = "No destination ID found for hotels."
    except Exception as e:
        logger.error(f"Booking.com hotel error: {e}")
        hotel_info = "Hotels currently elusive, Sir."

    combined = f"{flight_info}\n\n{hotel_info}" if flight_info or hotel_info else "No travel options found, Sir."
    return combined

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
    logger.info("daily_brief function started")
    chat_id = getattr(context.job, 'chat_id', None) or context.user_data.get('chat_id')
    logger.info(f"daily_brief chat_id: {chat_id}")
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
        info = get_travel_info(entity)
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
            f"Provide a witty, dry, two-sentence analysis of these travel options (flights and hotels) for Sir: {data_for_ai}"
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
    logger.info("check_now command received")
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
