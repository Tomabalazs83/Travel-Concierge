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
    ContextTypes,
)

import google.generativeai as genai

# ─── CONFIGURATION ───────────────────────────────────────────────────────────────
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_KEY     = os.environ.get("GEMINI_KEY")
RAPIDAPI_KEY   = os.environ.get("RAPIDAPI_KEY")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Early exit if critical env var is missing
if not TELEGRAM_TOKEN:
    logger.critical("TELEGRAM_TOKEN is missing → cannot start bot")
    exit(1)

# ─── GEMINI SETUP ────────────────────────────────────────────────────────────────
ai_brain = None
try:
    if not GEMINI_KEY:
        logger.warning("GEMINI_KEY missing → chat & analysis will be disabled")
    else:
        genai.configure(api_key=GEMINI_KEY, transport='rest')
        ai_brain = genai.GenerativeModel("gemini-2.5-flash")
        logger.info("Gemini model initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize Gemini: {e}", exc_info=True)

# ─── FLIGHT SEARCH TOOL ──────────────────────────────────────────────────────────
def get_flight_price(dest_entity: str) -> str:
    today = dt.now()
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
            logger.warning(f"Flight API returned {res.status_code} for {dest_entity}")
            return f"API error ({res.status_code})"

        data = res.json()
        itineraries = data.get('itineraries', [])
        if not itineraries:
            return "No offers found"

        price_amount = itineraries[0].get('price', {}).get('amount')
        return f"€{price_amount}" if price_amount is not None else "Price missing"

    except Exception as e:
        logger.error(f"Flight search failed for {dest_entity}: {e}", exc_info=True)
        return "Search failed"

# ─── BOT HANDLERS ────────────────────────────────────────────────────────────────
async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if ai_brain is None:
        await update.message.reply_text(
            "Terribly sorry, Sir — my thinking apparatus is currently indisposed."
        )
        return

    user_text = update.message.text.strip()
    if not user_text:
        return

    user_id = update.effective_user.id
    now = dt.utcnow()
    THREE_MONTHS = timedelta(days=90)

    if 'chat_session' not in context.user_data:
        context.user_data['chat_session'] = ai_brain.start_chat(history=[])
        context.user_data['last_active'] = now
        logger.info(f"New chat session created for user {user_id}")

    chat_session = context.user_data['chat_session']

    if 'last_active' in context.user_data:
        last_active = context.user_data['last_active']
        if isinstance(last_active, dt) and (now - last_active) > THREE_MONTHS:
            logger.info(f"Auto-clearing stale session for user {user_id}")
            del context.user_data['chat_session']
            if 'last_active' in context.user_data:
                del context.user_data['last_active']
            context.user_data['chat_session'] = ai_brain.start_chat(history=[])
            chat_session = context.user_data['chat_session']
            await update.message.reply_text(
                "Our previous correspondence has gracefully retired to the archives, Sir.\n"
                "We begin anew — how may I assist you today?"
            )

    context.user_data['last_active'] = now

    try:
        response = chat_session.send_message(user_text)
        text = response.text.strip()
        await update.message.reply_text(text)
    except Exception as e:
        logger.error(f"Gemini chat error for user {user_id}: {e}", exc_info=True)
        await update.message.reply_text(
            "A regrettable disturbance in the ether, Sir. Shall we try again?"
        )

async def daily_brief(context: ContextTypes.DEFAULT_TYPE):
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

    try:
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

        analysis_prompt = (
            "You are a sophisticated British butler. "
            "Provide a witty, dry, two-sentence analysis of these flight prices for Sir: "
            f"{data_for_ai}"
        )

        try:
            if 'chat_session' in context.user_data:
                res = context.user_data['chat_session'].send_message(analysis_prompt)
            else:
                res = ai_brain.generate_content(analysis_prompt)
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"🎩 **Butler’s insight:**\n{res.text.strip()}",
                parse_mode='Markdown'
            )
        except Exception as analysis_err:
            logger.error(f"Analysis failed: {analysis_err}", exc_info=True)
            await context.bot.send_message(
                chat_id=chat_id,
                text="The analytical department appears to be taking tea at present, Sir."
            )

    except Exception as e:
        logger.error(f"daily_brief failed: {e}", exc_info=True)
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text="Regrettably, Sir, I encountered an unexpected difficulty while preparing your briefing."
            )
        except:
            pass

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    context.user_data['chat_id'] = chat_id

    await update.message.reply_text(
        "The Concierge is at your service, Sir.\n"
        "Use /check for an immediate briefing, or simply speak to me."
    )

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
    logger.info("Starting butler bot...")

    try:
        app = (
            ApplicationBuilder()
            .token(TELEGRAM_TOKEN)
            .get_updates_read_timeout(30)
            .get_updates_write_timeout(30)
            .get_updates_pool_timeout(30)
            .build()
        )

        app.add_handler(CommandHandler('start', start))
        app.add_handler(CommandHandler('check', check_now))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))

        logger.info("Bot handlers registered. Starting polling...")
        app.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True,
            poll_interval=0.5,
            timeout=20
        )

    except Exception as fatal:
        logger.critical(f"Fatal error during bot startup or polling: {fatal}", exc_info=True)
        raise
