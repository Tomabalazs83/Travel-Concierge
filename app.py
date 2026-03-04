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

def get_flight_price(dest_code):
    # Testing a slightly more universal date format (DD/MM/YYYY)
    url = "https://kiwi-com-cheap-flights.p.rapidapi.com/v2/search"
    params = {
        "fly_from": "AMS",
        "fly_to": dest_code,
        "date_from": "01/07/2026",
        "date_to": "15/07/2026", # Narrowed window for faster search
        "curr": "EUR",
        "adults": 1, # Simplified to 1 adult for testing
        "limit": 1
    }
    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": "kiwi-com-cheap-flights.p.rapidapi.com"
    }
    try:
        res = requests.get(url, headers=headers, params=params, timeout=20)
        if res.status_code == 403:
            return "Key Error (403 Forbidden)"
        if res.status_code != 200:
            return f"API Error ({res.status_code})"
            
        data = res.json()
        if 'data' in data and len(data['data']) > 0:
            price = data['data'][0]['price']
            return f"€{price}"
        return "No flights found for these dates"
    except Exception as e:
        return f"Request failed: {str(e)[:20]}"

async def daily_brief(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id
    # We'll use more common airport codes for the first test
    options = {"Hawaii (Honolulu)": "HNL", "Bali (Denpasar)": "DPS", "London": "LHR", "Birmingham": "BHX"}
    
    report = "🛎 **Travel Concierge Morning Briefing, Sir**\n\n"
    data_for_ai = ""
    
    for name, code in options.items():
        price = get_flight_price(code)
        report += f"✈️ **{name}**: {price}\n"
        data_for_ai += f"{name}: {price}. "

    await context.bot.send_message(chat_id=chat_id, text=report, parse_mode='Markdown')

    try:
        # Simplified AI call
        summary = ai_brain.generate_content(f"Analyze these travel prices: {data_for_ai}").text
        await context.bot.send_message(chat_id=chat_id, text=f"🎩 **Concierge's Analysis:**\n{summary}")
    except:
        await context.bot.send_message(chat_id=chat_id, text="*The analytical engine is still warming up, Sir.*")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Concierge active. Use /check, Sir.")

async def check_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Searching the global registries, Sir...")
    class DummyJob: chat_id = update.effective_chat.id
    context.job = DummyJob()
    await daily_brief(context)

if __name__ == '__main__':
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('check', check_now))
    app.run_polling()
