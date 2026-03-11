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
                "You are Jeeves, a sophisticated British butler. Always address the user as 'Sir'. "
                "Be witty, dry, and concise. You monitor travel to London Heathrow for Sir."
            )
        )
        logger.info("Concierge initialized with gemini-1.5-flash")
except Exception as e:
    logger.error(f"AI setup failed: {e}")

# ─── TRAVEL SEARCH TOOL ──────────────────────────────────────────────────────────
def get_london_travel_info() -> str:
    # Sir's confirmed dates
    outbound_date = "2026-07-01"
    return_date = "2026-07-10"
    dest_code = "LHR"

    url = "https://google-flights2.p.rapidapi.com/api/v1/searchFlights"
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
        
        # ─── RESTORED QUOTA LOGGING ───
        remaining = response.headers.get('X-RateLimit-Requests-Remaining', 'N/A')
        limit = response.headers.get('X-RateLimit-Requests-Limit', 'N/A')
        logger.info(f"RapidAPI Status: {response.status_code} | Quota: {remaining} / {limit}")
        
        if response.status_code == 200:
            data = response.json()
            # Log the first 500 chars of the data to see the structure if it fails
            logger.info(f"Data Preview: {str(data)[:500]}")
            
            itin = data.get("data", {}).get("itineraries", {})
            # Look specifically for 'topFlights' first
            flights = itin.get("topFlights", []) or itin.get("otherFlights", [])
            
            if not flights:
                return "The manifests are empty, Sir. The API suggests no flights are currently listed for those dates."

            # Extraction logic for the lead flight
            lead = flights[0]
            price = lead.get('price')
            
            # Formatting the price string
            price_str = f"€{price}" if price else "Price elusive"
            
            legs = lead.get("legs", [])
            if legs:
                out_leg = legs[0]
                airline = out_leg.get("airline", {}).get("name", "Carrier unknown")
                dep = out_leg.get("departureTime", "—")[:16].replace('T', ' ')
                arr = out_leg.get("arrivalTime", "—")[:16].replace('T', ' ')
                return f"💰 **{price_str}**\n🛫 Outbound: {dep} → {arr} ({airline})"
            
            return f"💰 **{price_str}** (Leg details obscured, Sir.)"
            
        return f"The API returned status {response.status_code}. The connection is a bit frayed."
            
    except Exception as e:
        logger.error(f"Search error: {e}")
        return "I am unable to reach the flight registry at this moment, Sir."

# ─── BOT HANDLERS ────────────────────────────────────────────────────────────────
async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if ai_brain is None: return
    user_text = update.message.text.strip()
    if not user_text: return
    if 'chat_session' not in context.user_data:
        context.user_data['chat_session'] = ai_brain.start_chat(history=[])
    try:
        response = context.user_data['chat_session'].send_message(user_text)
        await update.message.reply_text(response.text.strip())
    except Exception as e:
        logger.error(f"Chat error: {e}")

async def daily_brief(context: ContextTypes.DEFAULT_TYPE):
    chat_id = getattr(context.job, 'chat_id', None) or context.user_data.get('chat_id')
    if not chat_id: return
    await context.bot.send_message(chat_id=chat_id, text="Consulting the Heathrow manifests for July, Sir...")
    info = get_london_travel_info()
    report = f"🛎 **Travel Briefing, Sir**\n\n✈️ **London Heathrow**:\n{info}"
    await context.bot.send_message(chat_id=chat_id, text=report, parse_mode='Markdown')

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['chat_id'] = update.effective_chat.id
    await update.message.reply_text("The Concierge is at your service, Sir. Monitoring London Heathrow as requested.")
    # Clear and reschedule job
    jobs = context.job_queue.get_jobs_by_name('daily_check')
    for job in jobs: job.schedule_removal()
    context.job_queue.run_daily(daily_brief, time=datetime.time(hour=8, minute=0), chat_id=update.effective_chat.id, name='daily_check')

async def check_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['chat_id'] = update.effective_chat.id
    await daily_brief(context)

if __name__ == '__main__':
    if not TELEGRAM_TOKEN: exit(1)
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    # Clean start logic
    loop = asyncio.get_event_loop()
    loop.run_until_complete(app.bot.delete_webhook(drop_pending_updates=True))

    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('check', check_now))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), chat))

    logger.info("Bot starting...")
    app.run_polling(drop_pending_updates=True)
