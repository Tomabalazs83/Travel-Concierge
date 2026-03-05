import os, requests, datetime, logging
from datetime import datetime as dt, timedelta
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from google import genai  # The modern 2026 SDK

# --- 1. CONFIGURATION ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_KEY = os.environ.get("GEMINI_KEY")
RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

# --- 2. MODERN AI SETUP (SDK v2.0) ---
try:
    client = genai.Client(api_key=GEMINI_KEY)
    
    # 2026 PRO-TIP: Use the clean ID without 'models/' for the new Client.
    # gemini-2.5-flash-lite is the designated successor to the 3.1-lite preview.
    MODEL_ID = "gemini-2.5-flash-lite" 
    
    SYS_INSTR = "You are Jeeves, a sophisticated British butler. Address the user as 'Sir'. Be witty, dry, and concise."
    logger.info(f"Concierge initialized with {MODEL_ID}.")
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
        if not itineraries: return "No offers found for the period, Sir."
        itin = itineraries[0]
        price = f"€{itin.get('price', {}).get('amount', '—')}"
        
        # Simplified report for the briefing
        return f"Current leading offer: **{price}**."
    except Exception as e:
        logger.error(f"Search failed: {e}")
        return "The details are currently elusive, Sir."

# --- 4. HANDLERS ---
async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not client: return
    try:
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
    data_for_ai = ""
    for name, entity in options.items():
        info = get_cheapest_roundtrip_info(entity)
        report += f"✈️ **{name}**: {info}\n"
        data_for_ai += f"{name}: {info}. "
    
    await context.bot.send_message(chat_id=chat_id, text=report, parse_mode='Markdown')

    # THE ANALYTICAL ENGINE
    try:
        analysis_res = client.models.generate_content(
            model=MODEL_ID,
            config={'system_instruction': SYS_INSTR},
            contents=f"Provide a witty, two-sentence analysis of these flight prices for Sir: {data_for_ai}"
        )
        await context.bot.send_message(chat_id=chat_id, text=f"🎩 **Analysis:**\n{analysis_res.text}")
    except Exception as e:
        logger.error(f"Analysis error: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['chat_id'] = update.effective_chat.id
    await update.message.reply_text("The Concierge is at your service, Sir. Use /check for flights.")
    context.job_queue.run_daily(daily_brief, time=datetime.time(hour=8, minute=0), chat_id=update.effective_chat.id)

async def check_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['chat_id'] = update.effective_chat.id
    await daily_brief(context)

# --- 5. LAUNCH ---
if __name__ == '__main__':
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('check', check_now))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), chat))
    logger.info("Butler bot starting...")
    app.run_polling(drop_pending_updates=True)
