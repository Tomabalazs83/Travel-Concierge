import os, requests, datetime, logging
from datetime import datetime as dt, timedelta
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from google import genai

# ─── CONFIGURATION ───────────────────────────────────────────────────────────────
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_KEY = os.environ.get("GEMINI_KEY")
RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

# ─── MODERN AI SETUP ─────────────────────────────────────────────────────────────
try:
    # Ensure you are using the genai.Client from the 'google-genai' package
    client = genai.Client(api_key=GEMINI_KEY)
    
    # In the stable 2026 SDK, we use the model name directly
    MODEL_ID = "gemini-1.5-flash" 
    
    SYS_INSTR = "You are Jeeves, a sophisticated British butler. Address the user as 'Sir'. Be witty, dry, and concise."
    logger.info(f"Concierge initialized with {MODEL_ID}.")
except Exception as e:
    logger.error(f"AI Setup failed: {e}")
    client = None

# ─── FLIGHT SEARCH TOOL ──────────────────────────────────────────────────────────
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
            f_nums = [f"{s.get('airline', {}).get('code', '??')}{s.get('number', '')}" for s in sects]
            dep = (sects[0].get('local_departure') or "—")[:16].replace('T', ' ')
            arr = (sects[-1].get('local_arrival') or "—")[:16].replace('T', ' ')
            return ", ".join(f_nums), dep, arr, len(sects)-1

        out_f, out_d, out_a, out_s = parse_leg('outbound')
        ret_f, ret_d, ret_a, ret_s = parse_leg('inbound')
        
        return (f"💰 **{price}**\n🛫 **Outbound:** {out_d} → {out_a} ({out_f}, {out_s} stops)\n"
                f"🛬 **Return:** {ret_d} → {ret_a} ({ret_f}, {ret_s} stops)")
    except Exception as e:
        logger.error(f"Search error: {e}")
        return "The details are currently elusive, Sir."

# ─── BOT HANDLERS ────────────────────────────────────────────────────────────────
async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not client: return
    user_text = update.message.text.strip()

    if 'chat_session' not in context.user_data:
        context.user_data['chat_session'] = client.chats.create(
            model=MODEL_ID,
            config={'system_instruction': SYS_INSTR}
        )

    try:
        chat_session = context.user_data['chat_session']
        response = chat_session.send_message(user_text)
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
    data_for_ai = ""
    for name, entity in options.items():
        info = get_cheapest_roundtrip_info(entity)
        report += f"✈️ **{name}**:\n{info}\n\n"
        data_for_ai += f"{name}: {info}. "
    
    await context.bot.send_message(chat_id=chat_id, text=report, parse_mode='Markdown')

    try:
        # Get or create session to maintain history
        chat_session = context.user_data.get('chat_session')
        if not chat_session:
            chat_session = client.chats.create(model=MODEL_ID, config={'system_instruction': SYS_INSTR})
            context.user_data['chat_session'] = chat_session
            
        analysis_res = chat_session.send_message(f"Provide a witty, two-sentence analysis of these prices: {data_for_ai}")
        await context.bot.send_message(chat_id=chat_id, text=f"🎩 **Butler's insight:**\n{analysis_res.text}")
    except Exception as e:
        logger.error(f"Analysis error: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['chat_id'] = update.effective_chat.id
    # Reset chat session on /start
    context.user_data['chat_session'] = client.chats.create(model=MODEL_ID, config={'system_instruction': SYS_INSTR})
    await update.message.reply_text("The Concierge is at your service, Sir. I have cleared my local ledger for our fresh start.")
    
    # Remove existing jobs and reschedule
    jobs = context.job_queue.get_jobs_by_name('daily_check')
    for job in jobs: job.schedule_removal()
    context.job_queue.run_daily(daily_brief, time=datetime.time(hour=8, minute=0), chat_id=update.effective_chat.id, name='daily_check')

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
