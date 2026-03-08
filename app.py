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
    out_date = (today + timedelta(days=90)).strftime("%Y-%m-%d")
    ret_date = (today + timedelta(days=110)).strftime("%Y-%m-%d")

    # Google Flights internal numeric airport IDs (required instead of IATA codes)
    airport_id_map = {
        "AMS": "178239",   # Amsterdam Schiphol
        "HNL": "1488",     # Honolulu International
        "DPS": "1489",     # Denpasar Ngurah Rai (Bali)
        "LHR": "1461"      # London Heathrow
    }

    origin_id = airport_id_map.get("AMS", "")
    dest_id = airport_id_map.get(dest_entity.split(':')[-1].upper(), "")

    if not origin_id or not dest_id:
        return "Invalid airport mapping, Sir."

    conn = http.client.HTTPSConnection("google-flights-data.p.rapidapi.com")
    headers = {
        'x-rapidapi-key': RAPIDAPI_KEY,
        'x-rapidapi-host': "google-flights-data.p.rapidapi.com"
    }

    # Use the correct endpoint from your docs
    path = f"/flights/search-roundtrip?departureId={origin_id}&arrivalId={dest_id}&departureDate={out_date}&returnDate={ret_date}&adults=1&currency=EUR"

    try:
        conn.request("GET", path, headers=headers)
        res = conn.getresponse()
        data = res.read()
        logger.info(f"Google Flights API status for {dest_entity}: {res.status}")
        logger.info(f"Google Flights response preview: {data.decode('utf-8')[:500]}...")  # debug

        if res.status != 200:
            return f"API error ({res.status}), Sir. Details are elusive."

        try:
            response_json = json.loads(data)
            # Parsing - adjust based on actual response structure (check log preview)
            trips = response_json.get("trips", []) or response_json.get("flights", []) or response_json.get("results", [])
            if not trips:
                return "No offers found, Sir."

            cheapest = min(trips, key=lambda t: t.get("price", float("inf")))
            price = f"€{cheapest.get('price', '—')}"

            # Outbound leg
            outbound = cheapest.get("outbound", {}) or cheapest.get("departure", {})
            out_dep = outbound.get("departureTime", "—")[:16].replace('T', ' ')
            out_arr = outbound.get("arrivalTime", "—")[:16].replace('T', ' ')
            out_airline = outbound.get("airline", "—")
            out_flight = outbound.get("flightNumber", "—")
            out_stops = outbound.get("stops", 0)

            # Return leg
            inbound = cheapest.get("inbound", {}) or cheapest.get("return", {})
            in_dep = inbound.get("departureTime", "—")[:16].replace('T', ' ')
            in_arr = inbound.get("arrivalTime", "—")[:16].replace('T', ' ')
            in_airline = inbound.get("airline", "—")
            in_flight = inbound.get("flightNumber", "—")
            in_stops = inbound.get("stops", 0)

            return (
                f"💰 **{price}**\n"
                f"🛫 **Outbound:** {out_dep} → {out_arr} ({out_airline} {out_flight}, {out_stops} stops)\n"
                f"🛬 **Return:** {in_dep} → {in_arr} ({in_airline} {in_flight}, {in_stops} stops)"
            )
        except json.JSONDecodeError:
            return "API response malformed, Sir. Details are elusive."
    except Exception as e:
        logger.error(f"Flight search error for {dest_entity}: {e}")
        return "The details are currently elusive, Sir."

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
