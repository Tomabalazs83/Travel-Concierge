import os, requests, datetime, logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import google.generativeai as genai

# --- 1. CONFIGURATION ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_KEY = os.environ.get("GEMINI_KEY")
RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY")

# REFINED AI INITIALIZATION
try:
    genai.configure(api_key=GEMINI_KEY)
    # Using 'gemini-1.5-flash' which is the standard 2026 production model
    ai_brain = genai.GenerativeModel('gemini-1.5-flash')
except Exception as e:
    print(f"Initial AI Config Error: {e}")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

# --- 2. FLIGHT REGISTRY TOOL ---
def get_flight_price(dest_entity):
    url = "https://kiwi-com-cheap-flights.p.rapidapi.com/round-trip"
    params = {
        "source": "City:amsterdam_nl",
        "destination": dest_entity,
        "currency": "EUR",
        "locale": "en",
        "adults": 1,
        "handbags": 1,
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
    except Exception:
        return "Search failed"

# --- 3. CONCIERGE ACTIONS ---
async def daily_brief(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id if hasattr(context, 'job') and context.job else context.user_data.get('chat_id')
    if not chat_id: return

    options = {"Hawaii": "City:honolulu_hi_us", "Bali": "City:denpasar_id", "Aruba": "City:oranjestad_aw", "London": "City:london_gb"}
    
    await context.bot.send_message(chat_id=chat_id, text="Consulting the summer registries, Sir...")
    
    report = "🛎 **Travel Concierge Summer Briefing, Sir**\n\n"
    data_for_ai = ""
    for name, entity in options.items():
        price = get_flight_price(entity)
        report += f"✈️ **{name}**: {price}\n"
        data_for_ai += f"{name}: {price}. "
    
    await context.bot.send_message(chat_id=chat_id, text=report, parse_mode='Markdown')

    # THE ANALYSIS BLOCK
    try:
        prompt = f"You are a sophisticated British Butler. Analyze these flight prices from Amsterdam for your employer: {data_for_ai}. Be concise, witty, and recommend the best value. Address him as Sir."
        response = ai_brain.generate_content(prompt)
        await context.bot.send_message(chat_id=chat_id, text=f"🎩 **Concierge's Analysis:**\n{response.text}")
    except Exception as e:
        logger.error(f"AI Error: {e}")
        # Send the actual error to Telegram so we can see what's wrong
        error_msg = str(e)[:100]
        await context.bot.send_message(chat_id=chat_id, text=f"⚠️ *The analytical engine encountered a hitch: {error_msg}*")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Concierge active. Daily at 08:00. Use /check now, Sir.")
    context.user_data['chat_id'] = update.effective_chat.id
    context.job_queue.run_daily(daily_brief, time=datetime.time(hour=8, minute=0), chat_id=update.effective_chat.id)

async def check_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['chat_id'] = update.effective_chat.id
    await daily_brief(context)

if __name__ == '__main__':
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('check', check_now))
    app.run_polling()
