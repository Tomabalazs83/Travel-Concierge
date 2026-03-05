import os
import requests
import datetime
import logging
from datetime import datetime as dt, timedelta

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes
)

import google.generativeai as genai

# ─── CONFIGURATION ───────────────────────────────────────────────────────────────
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_KEY     = os.environ.get("GEMINI_KEY")
RAPIDAPI_KEY   = os.environ.get("RAPIDAPI_KEY")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

# ─── GEMINI SETUP ────────────────────────────────────────────────────────────────
try:
    genai.configure(api_key=GEMINI_KEY, transport='rest')
    # Use a model name known to be available in 2026
    ai_brain = genai.GenerativeModel("gemini-2.5-flash")
    logger.info("Gemini model initialized successfully")
except Exception as e:
    logger.error(f"Gemini setup failed: {e}")
    ai_brain = None  # we'll check this later

# ─── FLIGHT SEARCH TOOL ──────────────────────────────────────────────────────────
def get_flight_price(dest_entity: str) -> str:
    """Query Kiwi.com RapidAPI for cheapest round-trip from Amsterdam"""
    today = dt.now()
    
    # Looking ~3–5 months ahead (adjust windows as desired)
    out_start = (today + timedelta(days=90)).strftime("%Y-%m-%dT00:00:00")
    out_end   = (today + timedelta(days=105)).strftime("%Y-%m-%dT00:00:00")
    in_start  = (today + timedelta(days=110)).strftime("%Y-%m-%dT00:00:00")
    in_end    = (today + timedelta(days=150)).strftime("%Y-%m-%dT00:00:00")

    url = "https://kiwi-com-cheap-flights.p.rapidapi.com/round-trip"
    
    params = {
        "source": "City:amsterdam_nl",
        "destination": dest_entity,
        "currency": "EUR",
        "locale": "en",
        "adults": 1,
        "cabinClass": "ECONOMY",
        "sortBy": "PRICE",
        "sortOrder": "ASCENDING",
        # You can remove or change this if the API doesn't like weekday filters
        "outbound": "SUNDAY,MONDAY,TUESDAY,WEDNESDAY,THURSDAY,FRIDAY,SATURDAY",
        "outboundDepartmentDateStart": out_start,
        "outboundDepartmentDateEnd":   out_end,
        "inboundDepartureDateStart":   in_start,
        "inboundDepartureDateEnd":     in_end,
        "limit": 1
    }

    headers = {
        "x-rapidapi-key": RAPIDAPI_KEY,
        "x-rapidapi-host": "kiwi-com-cheap-flights.p.rapidapi.com"
    }

    try:
        res = requests.get(url, headers=headers, params=params, timeout=18)
        if res.status_code != 200:
            return f"API error ({res.status_code})"

        data = res.json()
        itineraries = data.get('itineraries', [])
        if not itineraries:
            return "No offers found"

        price_amount = itineraries[0].get('price', {}).get('amount')
        return f"€{price_amount}" if price_amount else "Price missing"

    except Exception as e:
        logger.error(f"Flight search failed for {dest_entity}: {e}")
        return "Search failed"

# ─── BOT HANDLERS ────────────────────────────────────────────────────────────────
async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """General conversation with the butler"""
    if ai_brain is None:
        await update.message.reply_text(
            "I'm terribly sorry, Sir — my mind seems to be offline at the moment."
        )
        return

    user_text = update.message.text.strip()
    if not user_text:
        return

    try:
        prompt = f"You are a sophisticated British butler. Address the user as Sir. Keep replies elegant, concise and slightly dryly humorous when appropriate. Respond to: {user_text}"
        response = ai_brain.generate_content(prompt)
        text = response.text.strip()
        await update.message.reply_text(text)
    except Exception as e:
        logger.error(f"Gemini chat error: {e}")
        await update.message.reply_text(
            "My apologies, Sir. A momentary lapse in decorum occurred in the thinking apparatus."
        )

async def daily_brief(context: ContextTypes.DEFAULT_TYPE):
    """Morning flight price briefing"""
    # More robust chat_id retrieval
    chat_id = (
        getattr(context.job, 'chat_id', None)
        or context.user_data.get('chat_id')
    )
    if not chat_id:
        logger.warning("daily_brief called without chat_id")
        return

    options = {
        "Hawaii":  "City:honolulu_hi_us",
        "Bali":    "City:denpasar_id",
        "Aruba":   "City:oranjestad_aw",
        "London":  "City:london_gb"
    }

    await context.bot.send_message(chat_id=chat_id, text="Consulting the summer registries, Sir...")

    report = "🛎 **Travel Concierge Summer Briefing, Sir**\n\n"
    data_for_ai = ""

    for name, entity in options.items():
        price = get_flight_price(entity)
        report += f"✈️ **{name}**: {price}\n"
        data_for_ai += f"{name}: {price}. "

    await context.bot.send_message(
        chat_id=chat_id,
        text=report,
        parse_mode='Markdown'
    )

    if ai_brain is None:
        await context.bot.send_message(
            chat_id=chat_id,
            text="The analytical engine is indisposed this morning, Sir."
        )
        return

    try:
        analysis_prompt = (
            "You are a sophisticated British butler. "
            "Provide a witty, dry, two-sentence commentary on these flight prices for Sir:\n"
            f"{data_for_ai}"
        )
        res = ai_brain.generate_content(analysis_prompt)
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"🎩 **Butler’s insight:**\n{res.text.strip()}",
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Analysis failed: {e}")
        await context.bot.send_message(
            chat_id=chat_id,
            text="The analytical department appears to be taking tea at present, Sir."
        )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    context.user_data['chat_id'] = chat_id

    await update.message.reply_text(
        "The Concierge is at your service, Sir.\n"
        "Use /check for an immediate briefing, or simply speak to me."
    )

    # Remove old jobs to prevent duplicates
    current_jobs = context.job_queue.get_jobs_by_name('daily_flight_check')
    for job in current_jobs:
        job.schedule_removal()

    context.job_queue.run_daily(
        callback=daily_brief,
        time=datetime.time(hour=8, minute=0),
        chat_id=chat_id,
        name='daily_flight_check'
    )

async def check_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['chat_id'] = update.effective_chat.id
    await daily_brief(context)

# ─── MAIN ────────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    if not TELEGRAM_TOKEN:
        logger.error("TELEGRAM_TOKEN environment variable missing")
        exit(1)

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('check', check_now))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))

    logger.info("Butler bot starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)
