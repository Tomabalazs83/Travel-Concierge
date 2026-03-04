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
    
    # Using the date format most commonly successful in v1 deployments
    params = {
        "source": "City:amsterdam_nl",
        "destination": dest_entity,
        "currency": "EUR",
        "adults": 1,
        "cabinClass": "ECONOMY",
        "maxStopsCount": 2, # Essential for Bali/Hawaii
        "outboundDepartmentDateStart": "2026-07-01",
        "outboundDepartmentDateEnd": "2026-07-07",
        "inboundDepartureDateStart": "2026-07-20",
        "inboundDepartureDateEnd": "2026-07-27",
        "sortBy": "PRICE",
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
            if data.get('data') and len(data['data']) > 0:
                # v1 price can be a flat number or an object
                price_data = data['data'][0].get('price')
                amount = price_data.get('amount') if isinstance(price_data, dict) else price_data
                return f"€{amount}"
            return "No inventory (Dates restricted)"
        return f"Error {res.status_code}"
    except Exception as e:
        return "Search failed"

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
