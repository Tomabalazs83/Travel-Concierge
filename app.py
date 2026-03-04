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
    # Updated to the exact URL from Sir's snippet
    url = "https://kiwi-com-cheap-flights.p.rapidapi.com/round-trip"
    
    # Mirroring the exact parameters from the snippet
    params = {
        "source": "City:amsterdam_nl",  # Source for Sir in AMS
        "destination": dest_entity,
        "currency": "EUR",
        "locale": "en",
        "adults": "1",
        "children": "0",
        "infants": "0",
        "handbags": "1",
        "holdbags": "0",
        "cabinClass": "ECONOMY",
        "sortBy": "QUALITY",
        "sortOrder": "ASCENDING",
        "limit": "1"
    }
    
    headers = {
        "x-rapidapi-key": RAPIDAPI_KEY,
        "x-rapidapi-host": "kiwi-com-cheap-flights.p.rapidapi.com"
    }

    try:
        res = requests.get(url, headers=headers, params=params, timeout=20)
        if res.status_code == 200:
            data = res.json()
            # The snippet implies a list of flights under 'data'
            if data.get('data') and len(data['data']) > 0:
                price = data['data'][0].get('price', {}).get('amount', 'N/A')
                return f"€{price}"
            return "No offers found"
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
