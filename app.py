import os, requests, datetime, logging
from datetime import datetime as dt, timedelta
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from google import genai # The 2026 Modern SDK

# --- 1. CONFIGURATION ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_KEY = os.environ.get("GEMINI_KEY")
RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

# --- 2. MODERN AI SETUP (SDK v2.0) ---
try:
    client = genai.Client(api_key=GEMINI_KEY)
    MODEL_ID = "gemini-2.0-flash"
    # Instructions are passed per-request or per-session in the new SDK
    SYS_INSTR = "You are Jeeves, a sophisticated British butler. Address the user as 'Sir'. Be witty and concise."
    logger.info("Gemini 2.0 client initialized successfully.")
except Exception as e:
    logger.error(f"AI Setup failed: {e}")
    client = None

# --- 3. FLIGHT SEARCH TOOL ---
def get_cheapest_roundtrip_info(dest_entity: str) -> str:
    today = dt.now()
    out_start = (today + timedelta(days=90)).strftime("%Y-%m-%dT00:00:00")
    out_end   = (today + timedelta(days=105)).strftime("%Y-%m-%dT00:00:00")
    in_start  = (today + timedelta(days=110)).strftime("%Y-%m-%dT00:00:00")
    in_end    = (today + timedelta(days=150)).strftime("%Y-%m-%dT00:00:00")

    url = "https://kiwi-com-cheap-flights.p.rapidapi.com/round-trip"
    params = {
        "source": "City:amsterdam_nl", "destination": dest_entity, "currency": "EUR", "limit": 1,
        "outboundDepartmentDateStart": out_start, "outboundDepartmentDateEnd": out_end,
        "inboundDepartureDateStart": in_start, "inboundDepartureDateEnd": in_end
    }
    headers = {"x-rapidapi-key": RAPIDAPI_KEY, "x-rapidapi-host": "kiwi-com-cheap-flights.p.rapidapi.com"}

    try:
        res = requests.get(url, headers=headers, params=params, timeout=20)
        data = res.json()
        itineraries = data.get('itineraries') or data.get('data', {}).get('itineraries') or []
        
        if not itineraries: return "No offers found, Sir."
        itin = itineraries[0]
        price = f"€{itin.get('price', {}).get('amount', '—')}"

        def parse_leg(leg_name):
            leg = itin.get(leg_name, {})
            sects = leg.get('sectors', [])
            if not sects: return "N/A", "—", "—", 0
            
            f_nums = []
            for s in sects:
                air = s.get('airline', {})
                code = air.get('code') if isinstance(air, dict) else air
                f_nums.append(f"{code}{s.get('number', '')}")
            
            def fmt(t):
                try: return dt.fromisoformat(t.replace('Z', '')).strftime("%d %b, %H:%M")
                except: return str(t)[:16]

            dep = fmt(sects[0].get('local_departure') or sects[0].get('departure'))
            arr = fmt(sects[-1].get('local_arrival') or sects[-1].get('arrival'))
            return ", ".join(f_nums), dep, arr, len(sects)-1

        out_f, out_d, out_a, out_s = parse_leg('outbound')
        ret_f, ret_d, ret_a, ret_s = parse_leg('inbound')
        
        link = f"https://www.kiwi.com/en/booking?token={itin.get('id')}" if itin.get('id') else ""
        return (f"💰 **{price}**\n🛫 **Outbound:** {out_d} → {out_a} ({out_f}, {out_s} stops)\n"
                f"🛬 **Return:** {ret_d} → {ret_a} ({ret_f}, {ret_s} stops)\n🔗 [Book]({link})")
    except Exception as e:
        logger.error(f"Search error: {e}")
        return "The details are currently elusive, Sir."

# --- 4. HANDLERS ---
async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not client: return
    try:
        # The new SDK 2.0 pattern for simple chat
        response = client.models.generate_content(
            model=MODEL_ID,
            config={'system_instruction': SYS_INSTR},
            contents=update.message.text
        )
        await update.message.reply_text(response.text)
    except Exception as e:
        logger.error(f"Chat error: {e}")
        await update.message.reply_text("I'm dreadfully sorry, Sir, my thoughts are a bit muddled.")

async def daily_brief(context: ContextTypes.DEFAULT_TYPE):
    chat_id = getattr(context.job, 'chat_id', None) or context.user_data.get('chat_id')
    if not chat_id: return
    options = {"Hawaii": "City:honolulu_hi_us", "Bali": "City:denpasar_id", "London": "City:london_gb"}
    
    await context.bot.send_message(chat_id=chat_id, text="Consulting the summer registries, Sir...")
    report = "🛎 **Travel Briefing, Sir**\n\n"
    for name, entity in options.items():
        report += f"✈️ **{name}**:\n{get_cheapest_roundtrip_info(entity)}\n\n"
    await context.bot.send_message(chat_id=chat_id, text=report, parse_mode='Markdown')

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['chat_id'] = update.effective_chat.id
    await update.message.reply_text("The Concierge is at your service, Sir.")
    context.job_queue.run_daily(daily_brief, time=datetime.time(hour=8, minute=0), chat_id=update.effective_chat.id)

async def check_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['chat_id'] = update.effective_chat.id
    await daily_brief(context)

if __name__ == '__main__':
    # Initialize the app with a slight delay to help prevent 409 Conflicts on Railway
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('check', check_now))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), chat))
    logger.info("Butler bot starting...")
    app.run_polling(drop_pending_updates=True)
