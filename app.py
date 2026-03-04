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
    url = "https://kiwi-com-cheap-flights.p.rapidapi.com/round-trip"  # seems correct from playground references

    params = {
        "fly_from": "AMS",                           # IATA is safest starting point
        "fly_to": dest_entity,
        "date_from": "01/07/2026",
        "date_to": "15/07/2026",
        "return_from": "20/07/2026",
        "return_to": "05/08/2026",
        "curr": "EUR",
        "adults": "1",
        "max_stopovers": "2",
        "limit": "3",                                # ask for more than 1 → easier to see if anything comes back
    }

    headers = {
        "x-rapidapi-key": RAPIDAPI_KEY,
        "x-rapidapi-host": "kiwi-com-cheap-flights.p.rapidapi.com"
    }

    try:
        res = requests.get(url, headers=headers, params=params, timeout=20)

        # ── Very important: add logging ──
        logger.info(f"Request URL: {res.url}")
        logger.info(f"Status: {res.status_code}")
        if res.status_code != 200:
            logger.warning(f"Response body: {res.text[:800]}")  # first chunk

        if res.status_code == 200:
            data = res.json()
            logger.info(f"Response keys: {list(data.keys())}")

            if 'data' in data and data['data']:
                first = data['data'][0]
                # Try different possible price locations (wrapper variations)
                price = (
                    first.get('price', {}).get('amount')
                    or first.get('price')
                    or first.get('conversion', {}).get('EUR')
                    or first.get('fare', {}).get('amount')
                )
                if price:
                    return f"€{price}"
                return "Found result but no price field"
            return "No data[] results"
        return f"HTTP {res.status_code}"

    except Exception as e:
        logger.error(f"Exception: {str(e)}")
        return "Request failed"

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
