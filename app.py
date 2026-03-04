import os, requests, datetime, logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import google.generativeai as genai

# --- 1. CONFIGURATION ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_KEY = os.environ.get("GEMINI_KEY")
RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY")

# REFINED AI INITIALIZATION
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

try:
    # Explicitly using 'rest' transport to avoid 404/gRPC issues on Railway
    genai.configure(api_key=GEMINI_KEY, transport='rest')
    ai_brain = genai.GenerativeModel(
        model_name="gemini-1.5-flash",
        generation_config={"temperature": 0.7}
    )
except Exception as e:
    logger.error(f"AI Setup Error: {e}")

# --- 2. FLIGHT REGISTRY TOOL ---
def get_flight_price(dest_entity):
    url = "https://kiwi-com-cheap-flights.p.rapidapi.com/round-trip"
    params = {
        "source": "City:amsterdam_nl",
        "destination": dest_entity,
        "currency": "EUR",
        "locale": "en",
        "adults": 1,
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

    try:
        prompt = f"As a polite British Butler, summarize these travel prices for Sir: {data_for_ai}. Be witty and recommend the best value."
        # Use the modern .generate_content call
        response = ai_brain.generate_content(prompt)
        await context.bot.send_message(chat_id=chat_id, text=f"🎩 **Concierge's Analysis:**\n{response.text}")
    except Exception as e:
        logger.error(f"AI Error: {e}")
        await context.bot.send_message(chat_id=chat_id, text=f"⚠️ *The engine reports: {str(e)[:50]}...*")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Concierge active. Daily at 08:00. Use /check now, Sir.")
    context.user_data['chat_id'] = update.effective_chat.id
    # Clear old jobs before starting a new one
    current_jobs = context.job_queue.get_jobs_by_name('daily_flight_check')
    for job in current_jobs: job.schedule_removal()
    
    context.job_queue.run_daily(
        daily_brief, 
        time=datetime.time(hour=8, minute=0), 
        chat_id=update.effective_chat.id,
        name='daily_flight_check'
    )

async def check_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['chat_id'] = update.effective_chat.id
    await daily_brief(context)

if __name__ == '__main__':
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('check', check_now))
    app.run_polling()
