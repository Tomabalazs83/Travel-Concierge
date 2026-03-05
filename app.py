import os, requests, datetime, logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import google.generativeai as genai

# --- 1. CONFIGURATION (MARCH 2026 STANDARDS) ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_KEY = os.environ.get("GEMINI_KEY")
RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY")

# Logging setup for Railway console monitoring
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

try:
    # Using 'rest' transport is essential for stability on Railway
    genai.configure(api_key=GEMINI_KEY, transport='rest')
    # Stable 2026 model identifier
    ai_brain = genai.GenerativeModel(model_name="models/gemini-1.5-flash")
except Exception as e:
    logger.error(f"AI Setup Error: {e}")

# --- 2. FLIGHT REGISTRY TOOL ---
def get_flight_price(dest_entity):
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
        "outboundDepartmentDateStart": "2026-07-01T00:00:00",
        "outboundDepartmentDateEnd": "2026-07-15T00:00:00",
        "inboundDepartureDateStart": "2026-07-20T00:00:00",
        "inboundDepartureDateEnd": "2026-08-05T00:00:00",
        "limit": 1
    }
    headers = {
        "x-rapidapi-key": RAPIDAPI_KEY,
        "x-rapidapi-host": "kiwi-com-cheap-flights.p.rapidapi.com"
    }
    try:
        res = requests.get(url, headers=headers, params=params, timeout=20)
        if res.status_code == 200:
            data = res.json()
            itineraries = data.get('itineraries', [])
            if itineraries:
                price_obj = itineraries[0].get('price', {})
                return f"€{price_obj.get('amount')}"
            return "No live offers"
        return f"Error {res.status_code}"
    except Exception as e:
        logger.error(f"Price search error: {e}")
        return "Search failed"

# --- 3. CONCIERGE ACTIONS ---

async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles general conversation, Sir."""
    user_text = update.message.text
    try:
        # Instruction for the Butler persona
        prompt = f"You are a sophisticated British Butler named Gemini. Always address the user as Sir. Answer this query politely and helpfully: {user_text}"
        response = ai_brain.generate_content(prompt)
        
        if response and response.text:
            await update.message.reply_text(response.text)
        else:
            await update.message.reply_text("I'm afraid I have no words for that at the moment, Sir.")
            
    except Exception as e:
        logger.error(f"Chat Error: {e}")
        await update.message.reply_text(f"I'm dreadfully sorry, Sir, my thoughts are a bit muddled. (Error: {str(e)[:50]})")

async def daily_brief(context: ContextTypes.DEFAULT_TYPE):
    """The formal morning briefing or manual check, Sir."""
    chat_id = context.job.chat_id if hasattr(context, 'job') and context.job else context.user_data.get('chat_id')
    if not chat_id:
        return

    options = {
        "Hawaii": "City:honolulu_hi_us", 
        "Bali": "City:denpasar_id", 
        "Aruba": "City:oranjestad_aw", 
        "London": "City:london_gb"
    }
    
    await context.bot.send_message(chat_id=chat_id, text="Consulting the summer registries, Sir...")
    
    report = "🛎 **Travel Concierge Summer Briefing, Sir**\n\n"
    data_for_ai = ""
    for name, entity in options.items():
        price = get_flight_price(entity)
        report += f"✈️ **{name}**: {price}\n"
        data_for_ai += f"{name}: {price}. "
    
    await context.bot.send_message(chat_id=chat_id, text=report, parse_mode='Markdown')

    # THE ANALYSIS
    try:
        analysis_prompt = f"As a sophisticated British Butler, provide a witty 2-sentence analysis of these flight prices for Sir: {data_for_ai}"
        analysis_res = ai_brain.generate_content(analysis_prompt)
        if analysis_res and analysis_res.text:
            await context.bot.send_message(chat_id=chat_id, text=f"🎩 **Analysis:**\n{analysis_res.text}")
    except Exception as e:
        logger.error(f"Analysis Error: {e}")
        await context.bot.send_message(chat_id=chat_id, text="*The analytical engine is momentarily indisposed, Sir.*")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Initializes the service and the daily schedule, Sir."""
    await update.message.reply_text("The Concierge is at your service. Ask me anything or use /check for flights, Sir.")
    context.user_data['chat_id'] = update.effective_chat.id
    
    # Remove existing jobs to prevent duplicate briefings
    current_jobs = context.job_queue.get_jobs_by_name('daily_flight_check')
    for job in current_jobs:
        job.schedule_removal()
    
    # Schedule for 08:00 AM daily
    context.job_queue.run_daily(
        daily_brief, 
        time=datetime.time(hour=8, minute=0), 
        chat_id=update.effective_chat.id,
        name='daily_flight_check'
    )

async def check_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Triggers the briefing immediately, Sir."""
    context.user_data['chat_id'] = update.effective_chat.id
    await daily_brief(context)

# --- 4. LAUNCH PROTOCOL ---
if __name__ == '__main__':
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    # Command Handlers
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('check', check_now))
    
    # Message Handler for general conversation (must be registered last)
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), chat))
    
    logger.info("Concierge is standing by for your commands, Sir.")
    app.run_polling()
