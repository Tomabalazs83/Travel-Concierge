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
    
    # Matching the exact keys and ISO format from your snippet
    params = {
        "source": "City:amsterdam_nl",
        "destination": dest_entity,
        "currency": "EUR",
        "adults": 1,
        "handbags": 1,
        "cabinClass": "ECONOMY",
        "outboundDepartmentDateStart": "2026-07-01T00:00:00",
        "outboundDepartmentDateEnd": "2026-07-05T23:59:59",
        "inboundDepartureDateStart": "2026-07-15T00:00:00",
        "inboundDepartureDateEnd": "2026-07-20T23:59:59",
        "limit": 1
    }
    
    headers = {
        "x-rapidapi-key": RAPIDAPI_KEY,
        "x-rapidapi-host": "kiwi-com-cheap-flights.p.rapidapi.com"
    }

    try:
        res = requests.get(url, headers=headers, params=params, timeout=20)
        logger.info(f"API Call for {dest_entity}: Status {res.status_code}")
        
        if res.status_code == 200:
            data = res.json()
            # Navigating the v1 structure: data -> list -> price -> amount
            if data.get('data') and len(data['data']) > 0:
                price_obj = data['data'][0].get('price', {})
                # Some v1 responses use 'amount', others just return the number
                amount = price_obj.get('amount') if isinstance(price_obj, dict) else price_obj
                return f"€{amount}"
            return "No inventory found"
        return f"Error {res.status_code}"
    except Exception as e:
        return "Search error"

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
