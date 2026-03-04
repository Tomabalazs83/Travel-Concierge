import os, requests, datetime, logging, time
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import google.generativeai as genai

# --- 1. CONFIGURATION ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_KEY = os.environ.get("GEMINI_KEY")
RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY")

# Configure the AI Brain
genai.configure(api_key=GEMINI_KEY)
ai_brain = genai.GenerativeModel('gemini-1.5-flash')

# Set up the ledger (logging)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

# --- 2. FLIGHT REGISTRY TOOL ---
def get_flight_price(dest_code):
    logger.info(f"Querying v1 registry for {dest_code}...")
    # Using the exact v1 endpoint from your screenshot
    url = "https://kiwi-com-cheap-flights.p.rapidapi.com/v1/round-trip"
    
    params = {
        "fly_from": "AMS",
        "fly_to": dest_code,
        "date_from": "01/07/2026",
        "date_to": "05/07/2026",
        "return_from": "15/07/2026",
        "return_to": "20/07/2026",
        "curr": "EUR",
        "adults": "1"
    }
    
    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": "kiwi-com-cheap-flights.p.rapidapi.com"
    }
    
    try:
        res = requests.get(url, headers=headers, params=params, timeout=25)
        if res.status_code != 200:
            logger.error(f"Registry Error {res.status_code} for {dest_code}")
            return f"Service Error ({res.status_code})"
            
        data = res.json()
        # Parsing the v1 response structure
        if data.get('data') and len(data['data']) > 0:
            price = data['data'][0].get('price')
            return f"€{price}"
        
        return "Route Unavailable"
    except Exception as e:
        logger.error(f"System error during search: {e}")
        return "Search Failed"

# --- 3. THE CONCIERGE ACTIONS ---
async def daily_brief(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id
    # Using a mix of exotic and standard destinations for testing
    options = {"Hawaii": "HNL", "Bali": "DPS", "Aruba": "AUA", "London": "LHR"}
    
    header = "🛎 **Travel Concierge Morning Briefing, Sir**\n\n"
    # Send an initial message to the user
    await context.bot.send_message(chat_id=chat_id, text="Gathering the latest summer quotes, Sir...")
    
    report_lines = []
    data_for_ai = ""
    
    for name, code in options.items():
        price = get_flight_price(code)
        report_lines.append(f"✈️ **{name}**: {price}")
        data_for_ai += f"{name} is {price}. "
    
    full_report = header + "\n".join(report_lines)
    
    # Send the raw data first
    await context.bot.send_message(chat_id=chat_id, text=full_report, parse_mode='Markdown')

    # Attempt AI analysis
    try:
        ai_response = ai_brain.generate_content(f"Analyze these travel prices for a British gentleman: {data_for_ai}")
        await context.bot.send_message(chat_id=chat_id, text=f"🎩 **Analysis:**\n{ai_response.text}")
    except Exception as e:
        logger.error(f"AI Error: {e}")
        await context.bot.send_message(chat_id=chat_id, text="*The analytical engine is momentarily offline, Sir.*")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Your Travel Concierge is active, Sir. I shall monitor the routes daily at 08:00.")
    # Set the daily alarm
    context.job_queue.run_daily(daily_brief, time=datetime.time(hour=8, minute=0), chat_id=update.effective_chat.id)

async def check_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # This manually triggers the briefing
    class DummyJob: chat_id = update.effective_chat.id
    context.job = DummyJob()
    await daily_brief(context)

# --- 4. LAUNCH ---
if __name__ == '__main__':
    # Railway's direct connection allows for standard polling
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('check', check_now))
    
    logger.info("Concierge is standing by...")
    app.run_polling()
