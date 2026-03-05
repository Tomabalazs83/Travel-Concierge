import os
import requests
import datetime
import logging
import json
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

    SYSTEM_INSTRUCTION = """
    You are a sophisticated British butler named Jeeves. Always address the user as 'Sir'.
    Be elegant, concise, and slightly dryly humorous.
    You assist with travel planning and reference real-time flight data provided in the chat.
    When discussing flights, use the specific airlines, flight numbers, and times provided in the registry report.
    If Sir asks for more detail, explain that you have provided the primary itinerary but can look into alternative connections if he wishes.
    Stay fully in character at all times.
    """

    ai_brain = genai.GenerativeModel(
        "gemini-2.5-flash",
        system_instruction=SYSTEM_INSTRUCTION
    )
except Exception as e:
    logger.error(f"Gemini setup failed: {e}")
    ai_brain = None

# ─── FLIGHT SEARCH TOOL ──────────────────────────────────────────────────────────
def get_cheapest_roundtrip_info(dest_entity: str) -> str:
    """
    Extracts detailed itinerary info by parsing the 'route' array from the Kiwi API.
    """
    today = dt.now()
    # Setting search windows
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
        res = requests.get(url, headers=headers, params=params, timeout=20)
        res.raise_for_status()
        data = res.json()
        itineraries = data.get('itineraries', [])
        
        if not itineraries:
            return "No offers found for the selected period, Sir."

        itin = itineraries[0]
        route = itin.get('route', [])
        
        # 1. Price
        price = f"€{itin.get('price', {}).get('amount', '—')}"
        
        # 2. Split Route into Outbound (return=0) and Return (return=1)
        outbound_segments = [s for s in route if s.get('return') == 0]
        return_segments = [s for s in route if s.get('return') == 1]

        def parse_leg(segments):
            if not segments: return "No data", "—", "—", 0
            
            # Extract Flight Numbers (e.g., KL1234)
            flight_details = [f"{s.get('airline', '??')}{s.get('flight_no', '')}" for s in segments]
            
            # Times
            dep_time_raw = segments[0].get('local_departure', '—')
            arr_time_raw = segments[-1].get('local_arrival', '—')
            
            def format_dt(raw):
                try:
                    return dt.fromisoformat(raw.replace('Z', '')).strftime("%d %b, %H:%M")
                except:
                    return raw[:16]

            stops = len(segments) - 1
            return ", ".join(flight_details), format_dt(dep_time_raw), format_dt(arr_time_raw), stops

        out_flights, out_dep, out_arr, out_stops = parse_leg(outbound_segments)
        ret_flights, ret_dep, ret_arr, ret_stops = parse_leg(return_segments)

        # 3. Final String Construction
        book_link = itin.get('deep_link')
        link_part = f"\n🔗 [Secure Passage]({book_link})" if book_link else ""

        result = (
            f"💰 **{price}**\n"
            f"🛫 **Outbound:** {out_dep} → {out_arr}\n"
            f"   Flights: {out_flights} ({out_stops} stops)\n"
            f"🛬 **Return:** {ret_dep} → {ret_arr}\n"
            f"   Flights: {ret_flights} ({ret_stops} stops)\n"
            f"⏱ **Total Travel:** {itin.get('fly_duration', '—')}"
            f"{link_part}"
        )
        return result

    except Exception as e:
        logger.error(f"Flight processing failed: {e}")
        return "The registry details are currently obscured, Sir."

# ─── BOT HANDLERS ────────────────────────────────────────────────────────────────
async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if ai_brain is None:
        await update.message.reply_text("Terribly sorry, Sir — my grey matter is indisposed.")
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
        await update.message.reply_text("A most regrettable disturbance in the ether, Sir.")

async def daily_brief(context: ContextTypes.DEFAULT_TYPE):
    chat_id = getattr(context.job, 'chat_id', None) or context.user_data.get('chat_id')
    if not chat_id: return

    options = {"Hawaii": "City:honolulu_hi_us", "Bali": "City:denpasar_id", "Aruba": "City:oranjestad_aw", "London": "City:london_gb"}
    
    await context.bot.send_message(chat_id=chat_id, text="Consulting the summer registries, Sir...")

    report = "🛎 **Travel Concierge Summer Briefing, Sir**\n\n"
    data_for_ai = ""

    for name, entity in options.items():
        info = get_cheapest_roundtrip_info(entity)
        report += f"✈️ **{name}**:\n{info}\n\n"
        data_for_ai += f"{name}: {info}. "

    await context.bot.send_message(chat_id=chat_id, text=report, parse_mode='Markdown')

    try:
        prompt = f"Provide a witty, dry, two-sentence commentary on these offers for Sir:\n{data_for_ai}"
        res = ai_brain.generate_content(prompt)
        await context.bot.send_message(chat_id=chat_id, text=f"🎩 **Butler’s insight:**\n{res.text}", parse_mode='Markdown')
    except:
        pass

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['chat_id'] = update.effective_chat.id
    await update.message.reply_text("The Concierge is at your service, Sir. Use /check for a briefing.")
    
    current_jobs = context.job_queue.get_jobs_by_name('daily_flight_check')
    for job in current_jobs: job.schedule_removal()
    context.job_queue.run_daily(daily_brief, time=datetime.time(hour=8, minute=0), chat_id=update.effective_chat.id, name='daily_flight_check')

async def check_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['chat_id'] = update.effective_chat.id
    await daily_brief(context)

# ─── MAIN ────────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('check', check_now))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))
    app.run_polling()
