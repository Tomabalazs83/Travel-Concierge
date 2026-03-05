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
    today = dt.now()
    # 90-105 days out for summer planning
    out_start = (today + timedelta(days=90)).strftime("%Y-%m-%dT00:00:00")
    out_end   = (today + timedelta(days=105)).strftime("%Y-%m-%dT00:00:00")
    in_start  = (today + timedelta(days=110)).strftime("%Y-%m-%dT00:00:00")
    in_end    = (today + timedelta(days=150)).strftime("%Y-%m-%dT00:00:00")

    url = "https://kiwi-com-cheap-flights.p.rapidapi.com/round-trip"
    params = {
        "source": "City:amsterdam_nl",
        "destination": dest_entity,
        "currency": "EUR",
        "limit": 1,
        "outboundDepartmentDateStart": out_start,
        "outboundDepartmentDateEnd":   out_end,
        "inboundDepartureDateStart":   in_start,
        "inboundDepartureDateEnd":     in_end
    }
    headers = {"x-rapidapi-key": RAPIDAPI_KEY, "x-rapidapi-host": "kiwi-com-cheap-flights.p.rapidapi.com"}

    try:
        res = requests.get(url, headers=headers, params=params, timeout=20)
        res.raise_for_status()
        data = res.json()
        
        # Check if the response is wrapped in a 'data' key (common in 2026 versions)
        itineraries = data.get('itineraries') or data.get('data', {}).get('itineraries') or []
        
        if not itineraries:
            return "No offers found for the selected period, Sir."

        itin = itineraries[0]
        
        # LOGGING: Check your Railway logs for this line if details are still missing
        logger.info(f"Registry Keys for {dest_entity}: {list(itin.keys())}")
        
        # Attempt to find segments in 'route', 'sectors', or 'parts'
        segments = itin.get('route') or itin.get('sectors') or itin.get('parts') or []
        
        price = f"€{itin.get('price', {}).get('amount', '—')}"
        duration = itin.get('fly_duration') or itin.get('duration') or "—"
        
        if not segments:
            # Fallback to top-level airline codes if segments are hidden
            airlines = itin.get('airlines', []) or itin.get('airlines_codes', [])
            return (
                f"💰 **{price}**\n"
                f"⚠️ *The registry has restricted segment details for this route, Sir.*\n"
                f"✈️ **Carriers:** {', '.join(airlines) if airlines else 'Multiple'}\n"
                f"⏱ **Total Travel:** {duration}\n"
                f"🔗 [View Itinerary]({itin.get('deep_link')})"
            )

        # Separate segments by 'return' flag
        out_segs = [s for s in segments if s.get('return') == 0]
        ret_segs = [s for s in segments if s.get('return') == 1]

        def parse_leg(leg_segs):
            if not leg_segs: return "Details obscured", "—", "—", 0
            
            # Extract Airline + Flight Number (e.g., KL1234)
            f_nums = [f"{s.get('airline', '??')}{s.get('flight_no', '')}" for s in leg_segs]
            
            # Resilient time parsing (ISO or Unix)
            def get_time(s, key):
                val = s.get(f'local_{key}') or s.get(key) or s.get(f'{key[0]}Time')
                if isinstance(val, int): return dt.fromtimestamp(val).strftime("%d %b, %H:%M")
                try: return dt.fromisoformat(val.replace('Z', '')).strftime("%d %b, %H:%M")
                except: return str(val)[:16]

            dep = get_time(leg_segs[0], 'departure')
            arr = get_time(leg_segs[-1], 'arrival')
            return ", ".join(f_nums), dep, arr, len(leg_segs) - 1

        out_f, out_d, out_a, out_s = parse_leg(out_segs)
        ret_f, ret_d, ret_a, ret_s = parse_leg(ret_segs)

        return (
            f"💰 **{price}**\n"
            f"🛫 **Outbound:** {out_d} → {out_a}\n"
            f"   Flights: {out_f} ({out_s} stops)\n"
            f"🛬 **Return:** {ret_d} → {ret_a}\n"
            f"   Flights: {ret_f} ({ret_s} stops)\n"
            f"⏱ **Total Travel:** {duration}\n"
            f"🔗 [Secure Passage]({itin.get('deep_link')})"
        )

    except Exception as e:
        logger.error(f"Deep Registry Scan failed: {e}")
        return "The details are currently obscured within the registry, Sir."

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
