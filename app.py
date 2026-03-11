import os
import requests
import logging
import asyncio
import datetime
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
    if GEMINI_KEY:
        genai.configure(api_key=GEMINI_KEY)
        ai_brain = genai.GenerativeModel(
            "gemini-1.5-flash",
            system_instruction=(
                "You are Jeeves, a sophisticated British butler. "
                "Always address the user as 'Sir'. "
                "Be witty, dry, concise, and elegant. "
                "You are currently monitoring travel to London Heathrow for Sir."
            )
        )
        logger.info("Concierge initialized with gemini-1.5-flash")
except Exception as e:
    logger.error(f"AI setup failed: {e}")

# ─── TRAVEL SEARCH TOOL (google-flights2 API) ────────────────────────────────────
def get_london_travel_info() -> str:
    """
    Specifically targets London Heathrow for the dates Sir confirmed: July 1-10.
    """
    outbound_date = "2026-07-01"
    return_date = "2026-07-10"
    dest_code = "LHR"

    url = "https://google-flights2.p.rapidapi.com/api/v1/searchFlights"
    
    # Matching the exact parameters from the successful RapidAPI test
    querystring = {
        "departure_id": "AMS",
        "arrival_id": dest_code,
        "outbound_date": outbound_date,
        "return_date": return_date,
        "travel_class": "ECONOMY",
        "adults": "1",
        "currency": "EUR",
        "language_code": "en-US",
        "country_code": "NL"
    }

    headers = {
        "x-rapidapi-key": RAPIDAPI_KEY,
        "x-rapidapi-host": "google-flights2.p.rapidapi.com"
    }

    try:
        response = requests.get(url, headers=headers, params=querystring, timeout=30)
        logger.info(f"RapidAPI Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            # Navigate to the itineraries
            itin = data.get("data", {}).get("itineraries", {})
            
            # Combine all possible flight lists
            flights = itin.get("topFlights", []) or itin.get("otherFlights", [])
            
            if not flights:
                logger.warning("API returned Success but the flight lists are empty.")
                return "The registry is technically accessible, but contains no flight offers for those dates, Sir."

            # Select the first offer (Best/Cheapest)
            best_option = flights[0]
            price = f"€{best_option.get('price', '—')}"
            
            legs = best_option.get("legs", [])
            if legs:
                outbound = legs[0]
                airline = outbound.get("airline", {}).get("name", "Unknown Carrier")
                dep_time = outbound.get("departureTime", "—")[:16].replace('T', ' ')
                arr_time = outbound.get("arrivalTime", "—")[:16].replace('T', ' ')
                return f"💰 **{price}**\n🛫 Outbound: {dep_time} → {arr_time} ({airline})"
            
            return f"💰 **{price}** (Detailed leg info missing in registry, Sir.)"
            
        return f"The API returned a status of {response.status_code}, Sir. I suspect a disturbance in the network."
            
    except Exception as e:
        logger.error(f"Google Flights2 error: {e}")
        return "I encountered an error while consulting the flight manifests, Sir."

# ─── BOT HANDLERS ────────────────────────────────────────────────────────────────
async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if ai_brain is None:
        await update.message.reply_text("I'm dreadfully sorry, Sir, my thoughts are a bit muddled.")
        return

    user_text = update.message.text.strip()
    if not user_text: return

    if 'chat_session' not in context.user_data:
        context.user_data['chat_session'] = ai_brain.start_chat(history=[])

    try:
        response = context.user_data['chat_session'].send_message(user_text)
        await update.message.reply_text(response.text.strip())
    except Exception as e:
        logger.error(f"Chat error: {e}")
        await update.message.reply_text("A momentary lapse in decorum, Sir. Shall we try again?")

async def daily_brief(context: ContextTypes.DEFAULT_TYPE):
    chat_id = getattr(context.job, 'chat_id', None) or context.user_data.get('chat_id')
    if not chat_id: return

    await context.bot.send_message(chat_id=chat_id, text="Consulting the London registries for July, Sir...")

    # Focus strictly on London to save quota and avoid confusion
    info = get_london_travel_info()
    
    report = f"🛎 **Travel Briefing, Sir**\n\n✈️ **London Heathrow**:\n{info}"
    await context.bot.send_message(chat_id=chat_id, text=report, parse_mode='Markdown')

    if ai_brain:
        try:
            if 'chat_session' not in context.user_data:
                context.user_data['chat_session'] = ai_brain.start_chat(history=[])
            
            analysis_res = context.user_data['chat_session'].send_message(
                f"Analyze this flight data for London Heathrow for Sir: {info}. Keep it to two witty sentences."
            )
            await context.bot.send_message(
                chat_id=chat_id, 
                text=f"🎩 **Butler's insight:**\n{analysis_res.text.strip()}",
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Analysis error: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['chat_id'] = update.effective_chat.id
    context.user_data['chat_session'] = ai_brain.start_chat(history=[])
    await update.message.reply_text("The Concierge is at your service, Sir. I am focused strictly on your London Heathrow manifests.")

    # Schedule daily check
    jobs = context.job_queue.get_jobs_by_name('daily_check')
    for job in jobs: job.schedule_removal()
    context.job_queue.run_daily(daily_brief, time=datetime.time(hour=8, minute=0), chat_id=update.effective_chat.id, name='daily_check')

async def check_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['chat_id'] = update.effective_chat.id
    await daily_brief(context)

# ─── MAIN ────────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    if not TELEGRAM_TOKEN:
        exit(1)

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # Drop webhooks to ensure a fresh polling start
    loop = asyncio.get_event_loop()
    loop.run_until_complete(app.bot.delete_webhook(drop_pending_updates=True))

    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('check', check_now))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), chat))

    logger.info("Bot starting...")
    app.run_polling(drop_pending_updates=True)
