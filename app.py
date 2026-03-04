import os, requests, datetime, logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import google.generativeai as genai

# --- 1. CONFIGURATION ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_KEY = os.environ.get("GEMINI_KEY")
RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY")

# Configure the AI Brain with the explicit model path
genai.configure(api_key=GEMINI_KEY)
ai_brain = genai.GenerativeModel('models/gemini-1.5-flash')

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
        "children": 0,
        "infants": 0,
        "handbags": 1,
        "holdbags": 0,
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
                amount = price_obj.get('amount')
                return f"€{amount}"
            return "No live offers"
        return f"Error {res.status_code}"
    except Exception:
        return "Search failed"

# --- 3. CONCIERGE ACTIONS ---
async def daily_brief(context: ContextTypes.DEFAULT_TYPE):
    # Determine chat_id from job or manual trigger
    chat_id = context.job.chat_id if hasattr(context, 'job') and context.job else context.user_data.get('chat_id')
    
    if not chat_id:
        return

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
        data_for_ai += f"The price for {name} is {price}. "
    
    await context.bot.send_message(chat_id=chat_id, text=report, parse_mode='Markdown')

    try:
        prompt = f"You are a sophisticated British Butler. Analyze these flight prices for your employer: {data_for_ai}. Be concise, polite, and highlight the best value."
        summary = ai_brain.generate_content(prompt).text
        await context.bot.send_message(chat_id=chat_id, text=f"🎩 **Concierge's Analysis:**\n{summary}")
    except Exception as e:
        logger.error(f"AI Error: {e}")
        await context.bot.send_message(chat_id=chat_id, text="*The analytical engine is momentarily offline, Sir.*")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("The Concierge is active. Daily reports at 08:00, Sir. Use /check for immediate updates.")
    # Store chat_id for manual checks
    context.user_data['chat_id'] = update.effective_chat.id
    # Schedule the daily task
    context.job_queue.run_daily(daily_brief, time=datetime.time(hour=8, minute=0), chat_id=update.effective_chat.id)

async def check_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Set context chat_id and trigger
    context.user_data['chat_id'] = update.effective_chat.id
    await daily_brief(context)

# --- 4. LAUNCH ---
if __name__ == '__main__':
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('check', check_now))
    
    logger.info("Travel Concierge is standing by...")
    app.run_polling()
