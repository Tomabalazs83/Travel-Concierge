import os, requests, datetime, logging, json
from datetime import datetime as dt, timedelta
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import google.generativeai as genai

# ─── CONFIGURATION ───────────────────────────────────────────────────────────────
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_KEY     = os.environ.get("GEMINI_KEY")
RAPIDAPI_KEY   = os.environ.get("RAPIDAPI_KEY")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

# ─── GEMINI SETUP (2026 STANDARDS) ──────────────────────────────────────────────
try:
    # Using the stable 2026 endpoint to avoid 404 errors
    genai.configure(api_key=GEMINI_KEY, transport='rest')

    SYSTEM_INSTRUCTION = """
    You are a sophisticated British butler named Jeeves. Always address the user as 'Sir'.
    Be elegant, concise, and slightly dryly humorous.
    You assist with travel planning and reference real-time flight data provided in the chat.
    When flight details are mentioned, treat them as data you personally retrieved from the registries.
    If details are missing, politely recommend Sir check the booking link for the full manifest.
    """

    # Upgraded to 2.0 Flash for superior conversational speed and stability
    ai_brain = genai.GenerativeModel(
        model_name="gemini-2.0-flash",
        system_instruction=SYSTEM_INSTRUCTION
    )
    logger.info("Gemini 2.0 Flash initialized for Sir.")
except Exception as e:
    logger.error(f"Gemini setup failed: {e}")
    ai_brain = None

# ─── FLIGHT SEARCH TOOL (DEEP DIVE PARSING) ─────────────────────────────────────
def get_cheapest_roundtrip_info(dest_entity: str) -> str:
    today = dt.now()
    out_start = (today + timedelta(days=90)).strftime("%Y-%m-%dT00:00:00")
    out_end   = (today + timedelta(days=105)).strftime("%Y-%m-%dT00:00:00")
    in_start  = (today + timedelta(days=110)).strftime("%Y-%m-%dT00:00:00")
    in_end    = (today + timedelta(days=150)).strftime("%Y-%m-%dT00:00:00")

    url = "https://kiwi-com-cheap-flights.p.rapidapi.com/round-trip"
    params = {
        "source": "City:amsterdam_nl", "destination": dest_entity, "currency": "EUR", 
        "limit": 1, "outboundDepartmentDateStart": out_start, "outboundDepartmentDateEnd": out_end,
        "inboundDepartureDateStart": in_start, "inboundDepartureDateEnd": in_end
    }
    headers = {"x-rapidapi-key": RAPIDAPI_KEY, "x-rapidapi-host": "kiwi-com-cheap-flights.p.rapidapi.com"}

    try:
        res = requests.get(url, headers=headers, params=params, timeout=20)
        res.raise_for_status()
        data = res.json()
        itineraries = data.get('itineraries') or data.get('data', {}).get('itineraries') or []
        
        if not itineraries: return "No live offers found in the registries, Sir."
        itin = itineraries[0]
        
        # Price and Duration
        price = f"€{itin.get('price', {}).get('amount', '—')}"
        total_dur = itin.get('fly_duration') or itin.get('duration') or "—"

        def parse_leg(leg_key):
            leg = itin.get(leg_key, {})
            # Deep dive into 'sectors' for flight numbers and exact times
            sectors = leg.get('sectors', [])
            if not sectors: return "Details obscured", "—", "—", 0
            
            f_nums = []
            for s in sectors:
                # Airline code + number (e.g., KL1234)
                air = s.get('airline', {})
                code = air.get('code') if isinstance(air, dict) else s.get('airline') or "??"
                num = s.get('number') or s.get('flight_no') or ""
                f_nums.append(f"{code}{num}")
            
            def fmt(t):
                if not t: return "—"
                try: return dt.fromisoformat(t.replace('Z', '')).strftime("%d %b, %H:%M")
                except: return str(t)[:16]

            dep = fmt(sectors[0].get('local_departure') or sectors[0].get('departure'))
            arr = fmt(sectors[-1].get('local_arrival') or sectors[-1].get('arrival'))
            return ", ".join(f_nums), dep, arr, len(sectors)-1

        out_f, out_dep, out_arr, out_s = parse_leg('outbound')
        ret_f, ret_dep, ret_arr, ret_s = parse_leg('inbound')

        # Link reconstruction using 'id' as the booking token
        link = f"https://www.kiwi.com/en/booking?token={itin.get('id')}" if itin.get('id') else ""
        link_str = f"\n🔗 [Secure Passage]({link})" if link else ""

        return (f"💰 **{price}**\n"
                f"🛫 **Outbound:** {out_dep} → {out_arr}\n   Flights: {out_f} ({out_s} stops)\n"
                f"🛬 **Return:** {ret_dep} → {ret_arr}\n   Flights: {ret_f} ({ret_s} stops)\n"
                f"⏱ **Duration:** {total_dur}{link_str}")

    except Exception as e:
        logger.error(f"Processing error for {dest_entity}: {e}")
        return "The details are currently elusive in the registry, Sir."

# ─── BOT HANDLERS ────────────────────────────────────────────────────────────────
async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not ai_brain: return
    user_text = update.message.text.strip()
    if 'chat_session' not in context.user_data:
        context.user_data['chat_session'] = ai_brain.start_chat(history=[])
    
    try:
        response = context.user_data['chat_session'].send_message(user_text)
        await update.message.reply_text(response.text)
    except Exception as e:
        logger.error(f"Chat error: {e}")
        await update.message.reply_text("I'm dreadfully sorry, Sir, my thoughts are a bit muddled.")

async def daily_brief(context: ContextTypes.DEFAULT_TYPE):
    chat_id = getattr(context.job, 'chat_id', None) or context.user_data.get('chat_id')
    if not chat_id: return
    options = {"Hawaii": "City:honolulu_hi_us", "Bali": "City:denpasar_id", "London": "City:london_gb"}
    
    await context.bot.send_message(chat_id=chat_id, text="Consulting the summer registries, Sir...")
    report = "🛎 **Travel Concierge Summer Briefing, Sir**\n\n"
    for name, entity in options.items():
        report += f"✈️ **{name}**:\n{get_cheapest_roundtrip_info(entity)}\n\n"
    
    await context.bot.send_message(chat_id=chat_id, text=report, parse_mode='Markdown')

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['chat_id'] = update.effective_chat.id
    await update.message.reply_text("The Concierge is at your service, Sir. Use /check for flights.")
    for job in context.job_queue.get_jobs_by_name('daily_flight_check'): job.schedule_removal()
    context.job_queue.run_daily(daily_brief, time=datetime.time(hour=8, minute=0), chat_id=update.effective_chat.id, name='daily_flight_check')

async def check_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['chat_id'] = update.effective_chat.id
    await daily_brief(context)

if __name__ == '__main__':
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('check', check_now))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), chat))
    logger.info("Butler bot starting...")
    app.run_polling(drop_pending_updates=True)
