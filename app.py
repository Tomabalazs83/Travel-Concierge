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

def get_flight_price(dest_entity):
    url = "https://kiwi-com-cheap-flights.p.rapidapi.com/round-trip"
    
    # Using ISO 8601 format (2026-07-22T00:00:00) as required by current v1 specs
    params = {
        "source": "City:amsterdam_nl",
        "destination": dest_entity,
        "outboundDepartmentDateStart": "2026-07-01T00:00:00",
        "outboundDepartmentDateEnd": "2026-07-07T00:00:00",
        "inboundDepartureDateStart": "2026-07-15T00:00:00",
        "inboundDepartureDateEnd": "2026-07-22T00:00:00",
        "currency": "EUR",
        "adults": "1",
        "limit": "1",
        "sortBy": "PRICE",
        "sortOrder": "ASCENDING"
    }
    
    headers = {
        "x-rapidapi-key": RAPIDAPI_KEY,
        "x-rapidapi-host": "kiwi-com-cheap-flights.p.rapidapi.com"
    }

    try:
        res = requests.get(url, headers=headers, params=params, timeout=20)
        if res.status_code == 200:
            data = res.json()
            # Navigate the specific v1 response structure
            if data.get('data') and len(data['data']) > 0:
                # v1 often nests price within a 'price' object
                offer = data['data'][0]
                price_val = offer.get('price', {}).get('amount') if isinstance(offer.get('price'), dict) else offer.get('price')
                return f"€{price_val}"
            return "No inventory found"
        return f"Status {res.status_code}"
    except Exception as e:
        return "Search error"

async def daily_brief(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id
    
    # Updated to use the 'Entity ID' format required by the v1 API
    options = {
        "Hawaii": "City:honolulu_hi_us",
        "Bali": "City:denpasar_id",
        "Aruba": "Country:AW",
        "Birmingham": "City:birmingham_gb"
    }
    
    await context.bot.send_message(chat_id=chat_id, text="Consulting the v1 registries with the new protocol, Sir...")
    
    report = "🛎 **Travel Concierge Summer Briefing, Sir**\n\n"
    data_for_ai = ""
    
    for name, entity_id in options.items():
        price = get_flight_price(entity_id)
        report += f"✈️ **{name}**: {price}\n"
        data_for_ai += f"{name}: {price}. "

    await context.bot.send_message(chat_id=chat_id, text=report, parse_mode='Markdown')

    try:
        summary = ai_brain.generate_content(f"Analyze these travel prices for Sir: {data_for_ai}").text
        await context.bot.send_message(chat_id=chat_id, text=f"🎩 **Analysis:**\n{summary}")
    except:
        pass

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Concierge online. Use /check, Sir.")

async def check_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    class DummyJob: chat_id = update.effective_chat.id
    context.job = DummyJob()
    await daily_brief(context)

if __name__ == '__main__':
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('check', check_now))
    app.run_polling()
