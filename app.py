import os, requests, datetime, logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import google.generativeai as genai

# --- 1. CONFIG ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_KEY = os.environ.get("GEMINI_KEY")
RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY")

genai.configure(api_key=GEMINI_KEY)
ai_brain = genai.GenerativeModel('gemini-1.5-flash')
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_flight_price(dest_entity):
    url = "https://kiwi-com-cheap-flights.p.rapidapi.com/round-trip"
   
    params = {
        "fly_from": "AMS",                           # ← changed to IATA – more reliable
        "fly_to": dest_entity,
        "date_from": "01/07/2026",                   # DD/MM/YYYY format – very common for Kiwi wrappers
        "date_to": "15/07/2026",
        "return_from": "20/07/2026",
        "return_to": "05/08/2026",
        "curr": "EUR",
        "adults": "1",
        "max_stopovers": "2",                        # Kiwi usually uses this spelling
        "cabin_class": "economy",                    # lowercase is safer
        "limit": "3",                                # ask for more → easier to debug
    }
   
    headers = {
        "x-rapidapi-key": RAPIDAPI_KEY,
        "x-rapidapi-host": "kiwi-com-cheap-flights.p.rapidapi.com"
    }
    
    try:
        res = requests.get(url, headers=headers, params=params, timeout=20)
        
        # ──────────────── ADD THESE LOG LINES HERE ────────────────
        logger.info(f"Requested URL: {res.url}")                    # shows final URL + query string
        logger.info(f"HTTP Status: {res.status_code}")
        
        if res.status_code != 200:
            logger.warning(f"Non-200 response body: {res.text[:1000]}")  # first part of error
            return f"Error {res.status_code}"
        
        data = res.json()
        
        # ──────────────── ADD THESE LOG LINES RIGHT AFTER json() ────────────────
        logger.info(f"Response top-level keys: {list(data.keys())}")
        
        if 'data' in data:
            logger.info(f"'data' length: {len(data['data'])}")
            if data['data']:
                first_result = data['data'][0]
                logger.info(f"First result keys: {list(first_result.keys())}")
                # Try to show possible price locations
                logger.info(f"Possible price fields → 'price': {first_result.get('price')}")
                logger.info(f"                   → 'fare': {first_result.get('fare')}")
                logger.info(f"                   → 'conversion': {first_result.get('conversion')}")
            else:
                logger.info("'data' exists but is empty []")
        else:
            logger.info("No 'data' key found in response")
        # ──────────────────────────────────────────────────────────────
        
        # Your original result handling (you can keep or adjust)
        if data.get('data') and len(data['data']) > 0:
            price_info = data['data'][0].get('price')
            amount = price_info.get('amount') if isinstance(price_info, dict) else price_info
            return f"€{amount}"
        return "No inventory / empty results"
        
    except Exception as e:
        logger.error(f"Request exception: {str(e)}")
        return "Registry unreachable"

async def daily_brief(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id
    # Using the 'City:name_cc' format as specified in your RapidAPI parameters
    options = {
        "Hawaii": "City:honolulu_hi_us",
        "Bali": "City:denpasar_id",
        "London": "City:london_gb",
        "Aruba": "City:oranjestad_aw"
    }
    
    await context.bot.send_message(chat_id=chat_id, text="Consulting the v1 registry with the new parameters, Sir...")
    
    report = "🛎 **Travel Concierge Summer Briefing, Sir**\n\n"
    for name, entity in options.items():
        price = get_flight_price(entity)
        report += f"✈️ **{name}**: {price}\n"
    
    await context.bot.send_message(chat_id=chat_id, text=report, parse_mode='Markdown')

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Concierge active. Use /check for updates, Sir.")

async def check_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    class DummyJob: chat_id = update.effective_chat.id
    context.job = DummyJob()
    await daily_brief(context)

if __name__ == '__main__':
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('check', check_now))
    app.run_polling()
