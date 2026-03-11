import os, requests, logging, asyncio, datetime
from datetime import datetime as dt
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import google.generativeai as genai

# ─── CONFIGURATION ───────────────────────────────────────────────────────────────
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_KEY = os.environ.get("GEMINI_KEY")
RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ─── AI SETUP ────────────────────────────────────────────────────────────────────
ai_brain = None
try:
    if GEMINI_KEY:
        genai.configure(api_key=GEMINI_KEY)
        ai_brain = genai.GenerativeModel(
            "gemini-1.5-flash",
            system_instruction="You are Jeeves, a dryly witty British butler. Address the user as 'Sir'."
        )
        logger.info("Concierge initialized.")
except Exception as e:
    logger.error(f"AI setup failed: {e}")

# ─── TRAVEL SEARCH TOOL (Aligned with Sir's Example) ─────────────────────────────
def get_london_travel_info() -> str:
    # Confirmed working dates: July 1 to July 10
    outbound_date, return_date = "2026-07-01", "2026-07-10"
    
    url = "https://google-flights2.p.rapidapi.com/api/v1/searchFlights"
    params = {
        "departure_id": "AMS", "arrival_id": "LHR",
        "outbound_date": outbound_date, "return_date": return_date,
        "travel_class": "ECONOMY", "adults": "1", "currency": "EUR",
        "language_code": "en-US", "country_code": "NL"
    }
    headers = {"x-rapidapi-key": RAPIDAPI_KEY, "x-rapidapi-host": "google-flights2.p.rapidapi.com"}

    try:
        response = requests.get(url, headers=headers, params=params, timeout=30)
        
        # ─── QUOTA TRACKING ───
        remaining = response.headers.get('X-RateLimit-Requests-Remaining', 'N/A')
        logger.info(f"RapidAPI: {response.status_code} | Quota Remaining: {remaining}")
        
        if response.status_code == 200:
            res_json = response.json()
            data_content = res_json.get("data", {})
            
            # According to Sir's example: data -> topFlights
            flights = data_content.get("topFlights", []) or data_content.get("otherFlights", [])
            
            if not flights:
                logger.warning(f"No flights in 'data'. Available keys: {list(data_content.keys())}")
                return "The flight manifest is currently empty for those dates, Sir."

            # Exact mapping from Sir's example JSON
            lead = flights[0]
            price = lead.get('price', '—')
            dep_time = lead.get('departure_time', '—')
            arr_time = lead.get('arrival_time', '—')
            
            # The airline is nested in the 'flights' segment list
            segments = lead.get('flights', [])
            airline = segments[0].get('airline', 'Unknown Carrier') if segments else "Carrier Unknown"
            
            return f"💰 **€{price}**\n🛫 Outbound: {dep_time}\n🛬 Arrival: {arr_time}\n✈️ {airline}"
            
        return f"The registry is indisposed (Status {response.status_code}), Sir."
    except Exception as e:
        logger.error(f"Flight search error: {e}")
        return "I encountered a disturbance while consulting the manifests, Sir."

# ─── BOT HANDLERS ────────────────────────────────────────────────────────────────
async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not ai_brain: return
    user_text = update.message.text.strip()
    if 'chat_session' not in context.user_data:
        context.user_data['chat_session'] = ai_brain.start_chat(history=[])
    try:
        response = context.user_data['chat_session'].send_message(user_text)
        await update.message.reply_text(response.text.strip())
    except Exception as e:
        logger.error(f"Chat error: {e}")

async def daily_brief(context: ContextTypes.DEFAULT_TYPE):
    chat_id = getattr(context.job, 'chat_id', None) or context.user_data.get('chat_id')
    if not chat_id: return
    await context.bot.send_message(chat_id=chat_id, text="Consulting the Heathrow manifests, Sir...")
    info = get_london_travel_info()
    await context.bot.send_message(chat_id=chat_id, text=f"🛎 **Briefing, Sir**\n\n{info}", parse_mode='Markdown')
    if ai_brain:
        try:
            chat_session = context.user_data.get('chat_session') or ai_brain.start_chat(history=[])
            res = chat_session.send_message(f"Flight data: {info}. Give a witty 2-sentence analysis.")
            await context.bot.send_message(chat_id=chat_id, text=f"🎩 **Insight:**\n{res.text.strip()}")
        except: pass

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['chat_id'] = update.effective_chat.id
    if ai_brain: context.user_data['chat_session'] = ai_brain.start_chat(history=[])
    await update.message.reply_text("The Concierge is at your service, Sir. Heathrow manifests are ready.")
    jobs = context.job_queue.get_jobs_by_name('daily_check')
    for job in jobs: job.schedule_removal()
    context.job_queue.run_daily(daily_brief, time=datetime.time(hour=8, minute=0), chat_id=update.effective_chat.id, name='daily_check')

async def check_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['chat_id'] = update.effective_chat.id
    await daily_brief(context)

if __name__ == '__main__':
    if not TELEGRAM_TOKEN: exit(1)
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    loop = asyncio.get_event_loop()
    loop.run_until_complete(app.bot.delete_webhook(drop_pending_updates=True))
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('check', check_now))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), chat))
    logger.info("Bot starting...")
    app.run_polling(drop_pending_updates=True)
