import os, requests, datetime, logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import google.generativeai as genai

# --- 1. CONFIGURATION ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_KEY = os.environ.get("GEMINI_KEY")
RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY")

# Configure the AI Brain
genai.configure(api_key=GEMINI_KEY)
ai_brain = genai.GenerativeModel('gemini-1.5-flash')

# Set up logging for the Railway console
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

# --- 2. FLIGHT REGISTRY TOOL ---
def get_flight_price(dest_entity):
    url = "https://kiwi-com-cheap-flights.p.rapidapi.com/round-trip"
    
    # Parameters matched to Sir's successful 200 OK logs
    params = {
        "fly_from": "AMS",
        "fly_to": dest_entity,
        "date_from": "01/07/2026",
        "date_to": "15/07/2026",
        "return_from": "20/07/2026",
        "return_to": "05/08/2026",
        "curr": "EUR",
        "adults": 1,
        "max_stopovers": 2,
        "cabin_class": "economy",
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
            # Navigating the 'itineraries' structure identified in the ledger
            itineraries = data.get('itineraries', [])
            if itineraries and len(itineraries) > 0:
                price_info = itineraries[0].get('price', {})
                amount = price_info.get('amount')
                return f"€{amount}" if amount else "Price detail missing"
            return "No itineraries found"
        return f"Service Error ({res.status_code})"
    except Exception as e:
        logger.error(f"Search failed for {dest_entity}: {e}")
        return "Search failed"

# --- 3. CONCIERGE ACTIONS ---
async def daily_brief(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id
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
    
    # Send the raw flight data
    await context.bot.send_message(chat_id=chat_id, text=report, parse_mode='Markdown')

    # Attempt AI summary
    try:
        summary = ai_brain.generate_content(f"Analyze these travel prices for a British gentleman: {data_for_ai}").text
        await context.bot.send_message(chat_id=chat_id, text=f"🎩 **Analysis:**\n{summary}")
    except Exception as e:
        logger.error(f"AI Error: {e}")
        await context.bot.send_message(chat_id=chat_id, text="*The analytical engine is momentarily offline, Sir.*")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("The Concierge is active. Daily reports at 08:00, Sir.")
    context.job_queue.run_daily(daily_brief, time=datetime.time(hour=8, minute=0), chat_id=update.effective_chat.id)

async def check_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Triggers the briefing immediately
    class DummyJob: chat_id = update.effective_chat.id
    context.job = DummyJob()
    await daily_brief(context)

# --- 4. LAUNCH ---
if __name__ == '__main__':
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('check', check_now))
    
    logger.info("Travel Concierge is standing by...")
    app.run_polling()
