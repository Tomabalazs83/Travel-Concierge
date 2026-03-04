import os, requests, datetime, logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from telegram.request import HTTPXRequest
import google.generativeai as genai

# --- 1. CONFIG ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_KEY = os.environ.get("GEMINI_KEY")
RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY")

genai.configure(api_key=GEMINI_KEY)
ai_brain = genai.GenerativeModel('gemini-1.5-flash')
logging.basicConfig(level=logging.INFO)

# --- 2. TOOLS ---
def get_flight_price(dest_code):
    url = "https://kiwi-com-cheap-flights.p.rapidapi.com/v2/search"
    params = {"fly_from": "AMS", "fly_to": dest_code, "date_from": "01/07/2026", "date_to": "31/08/2026", "nights_in_dst_from": 10, "curr": "EUR", "adults": 2, "children": 2}
    headers = {"X-RapidAPI-Key": RAPIDAPI_KEY, "X-RapidAPI-Host": "kiwi-com-cheap-flights.p.rapidapi.com"}
    try:
        res = requests.get(url, headers=headers, params=params, timeout=15).json()
        return f"€{res['data'][0]['price']}" if res.get('data') else "N/A"
    except: return "N/A"

# --- 3. ACTIONS ---
async def daily_brief(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id
    options = {"Hawaii": "HNL", "Bali": "DPS", "Aruba": "AUA", "Birmingham": "BHX"}
    report = "🛎 **Travel Concierge Morning Briefing, Sir**\n\n"
    data_for_ai = ""
    for name, code in options.items():
        p = get_flight_price(code)
        report += f"✈️ {name}: {p}\n"
        data_for_ai += f"{name}: {p}. "
    summary = ai_brain.generate_content(f"You are a British Concierge. Summarize: {data_for_ai}").text
    await context.bot.send_message(chat_id=chat_id, text=report + "\n" + summary, parse_mode='Markdown')

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("The Concierge is at your service, Sir. Use /check for updates.")
    context.job_queue.run_daily(daily_brief, time=datetime.time(hour=8, minute=0), chat_id=update.effective_chat.id)

async def check_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Consulting the charts, Sir...")
    class DummyJob: chat_id = update.effective_chat.id
    context.job = DummyJob()
    await daily_brief(context)

# --- 4. LAUNCH ---
if __name__ == '__main__':
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('check', check_now))
    print("Concierge is standing by...")
    app.run_polling()
