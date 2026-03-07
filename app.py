import os
import requests
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
GEMINI_KEY     = os.environ.get("GEMINI_KEY")
RAPIDAPI_KEY   = os.environ.get("RAPIDAPI_KEY")

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

# ─── FLIGHT SEARCH TOOL ──────────────────────────────────────────────────────────
def get_cheapest_roundtrip_info(dest_entity: str) -> str:
    today = dt.now()
    out_start = (today + timedelta(days=90)).strftime("%Y-%m-%d")
    out_end   = (today + timedelta(days=105)).strftime("%Y-%m-%d")
    in_start  = (today + timedelta(days=110)).strftime("%Y-%m-%d")
    in_end    = (today + timedelta(days=150)).strftime("%Y-%m-%d")

    url = "https://kiwi-com-cheap-flights.p.rapidapi.com/search"
    params = {
        "fly_from": "AMS",
        "fly_to": dest_entity.split(':')[-1].upper(),  # e.g. DPS for Bali
        "date_from": out_start,
        "date_to": out_end,
        "return_from": in_start,
        "return_to": in_end,
        "currency": "EUR",
        "adults": "1",
        "sort": "price",
        "limit": "1"
    }
    headers = {
        "x-rapidapi-key": RAPIDAPI_KEY,
        "x-rapidapi-host": "kiwi-com-cheap-flights.p.rapidapi.com"
    }

    try:
        res = requests.get(url, headers=headers, params=params, timeout=20)
        logger.info(f"Kiwi search API status for {dest_entity}: {res.status_code}")
        res.raise_for_status()
        data = res.json()
        logger.info(f"Kiwi raw response keys: {list(data.keys())}")  # debug

        itineraries = data.get('data', [])
        if not itineraries:
            return "No offers found in the selected window, Sir."

        itin = itineraries[0]
        price = f"€{itin.get('price', '—')}"

        # Parse outbound leg
        out_route = itin.get('route', [{}])[0]
        out_dep = out_route.get('local_departure', "—")[:16].replace('T', ' ')
        out_arr = out_route.get('local_arrival', "—")[:16].replace('T', ' ')
        out_airline = out_route.get('airline', "—")
        out_flight = out_route.get('flight_no', "—")
        out_stops = out_route.get('stops', 0)

        # Parse return leg
        in_route = itin.get('route', [{}])[1]
        in_dep = in_route.get('local_departure', "—")[:16].replace('T', ' ')
        in_arr = in_route.get('local_arrival', "—")[:16].replace('T', ' ')
        in_airline = in_route.get('airline', "—")
        in_flight = in_route.get('flight_no', "—")
        in_stops = in_route.get('stops', 0)

        return (
            f"💰 **{price}**\n"
            f"🛫 **Outbound:** {out_dep} → {out_arr} ({out_airline} {out_flight}, {out_stops} stops)\n"
            f"🛬 **Return:** {in_dep} → {in_arr} ({in_airline} {in_flight}, {in_stops} stops)"
        )
    except Exception as e:
        logger.error(f"Search error for {dest_entity}: {e}")
        return "The details are currently elusive, Sir. Perhaps try a different date range."

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
        info = get_cheapest_roundtrip_info(entity)
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
