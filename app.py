import os, requests, logging, asyncio, datetime
from datetime import datetime as dt
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from google import genai  # The 2026 Modern SDK

# ─── CONFIGURATION ───────────────────────────────────────────────────────────────
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_KEY = os.environ.get("GEMINI_KEY")
RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ─── MODERN AI SETUP (google-genai) ──────────────────────────────────────────────
client = None
MODEL_ID = "gemini-1.5-flash"
SYS_INSTR = "You are Jeeves, a sophisticated British butler. Always address the user as 'Sir'. Be witty, dry, and concise."

try:
    if GEMINI_KEY:
        client = genai.Client(api_key=GEMINI_KEY)
        logger.info(f"Concierge initialized with {MODEL_ID}")
except Exception as e:
    logger.error(f"AI setup failed: {e}")

# ─── TRAVEL SEARCH TOOL (Google Flights2 Schema) ────────────────────────────────
def get_london_travel_info() -> str:
    # Confirmed working dates from Sir's test
    outbound_date, return_date = "2026-07-01", "2026-07-10"
    dest_code = "LHR"

    url = "https://google-flights2.p.rapidapi.com/api/v1/searchFlights"
    params = {
        "departure_id": "AMS", "arrival_id": dest_code,
        "outbound_date": outbound_date, "return_date": return_date,
        "travel_class": "ECONOMY", "adults": "1", "currency": "EUR",
        "language_code": "en-US", "country_code": "NL"
    }

    headers = {"x-rapidapi-key": RAPIDAPI_KEY, "x-rapidapi-host": "google-flights2.p.rapidapi.com"}

    try:
        response = requests.get(url, headers=headers, params=params, timeout=30)
        
        # ─── QUOTA TRACKING ───
        remaining = response.headers.get('X-RateLimit-Requests-Remaining', 'N/A')
        limit = response.headers.get('X-RateLimit-Requests-Limit', 'N/A')
        logger.info(f"RapidAPI: {response.status_code} | Quota Remaining: {remaining}/{limit}")
        
        if response.status_code == 200:
            res_data = response.json()
            data_block = res_data.get("data", {})
            
            # Using Sir's verified JSON structure: data -> topFlights
            flights = data_block.get("topFlights", []) or data_block.get("otherFlights", [])
            
            if not flights:
                return "The flight manifest is currently empty for those dates, Sir."

            # Extract lead flight details
            lead = flights[0]
            price = lead.get('price', '—')
            dep_time = lead.get('departure_time', '—')
            arr_time = lead.get('arrival_time', '—')
            
            # Navigate to internal segment for airline name
            segments = lead.get('flights', [])
            airline = segments[0].get('airline', 'Unknown Carrier') if segments else "Carrier Unknown"
            
            return f"💰 **€{price}**\n🛫 Outbound: {dep_time}\n🛬 Arrival: {arr_time}\n✈️ {airline}"
            
        return f"The registry is indisposed (Status {response.status_code}), Sir."
    except Exception as e:
        logger.error(f"Flight search error: {e}")
        return "I encountered a disturbance while consulting the manifests, Sir."

# ─── BOT HANDLERS ────────────────────────────────────────────────────────────────
async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not client: return
    user_text = update.message.text.strip()
    if 'chat_session' not in context.user_data:
        context.user_data['chat_session'] = client.chats.create(model=MODEL_ID, config={'system_instruction': SYS_INSTR})

    try:
        response = context.user_data['chat_session'].send_message(user_text)
        await update.message.reply_text(response.text.strip())
    except Exception as e:
        logger.error(f"Chat error: {e}")

async def daily_brief(context: ContextTypes.DEFAULT_TYPE):
    chat_id = getattr(context.job, 'chat_id', None) or context.user_data.get('chat_id')
    if not chat_id: return
    
    await context.bot.send_message(chat_id=chat_id, text="Consulting the London Heathrow manifests, Sir...")
    info = get_london_travel_info()
    
    await context.bot.send_message(chat_id=chat_id, text=f"🛎 **Travel Briefing, Sir**\n\n{info}", parse_mode='Markdown')

    if client:
        try:
            chat_session = context.user_data.get('chat_session') or client.chats.create(model=MODEL_ID, config={'system_instruction': SYS_INSTR})
            res = chat_session.send_message(f"Sir's flight data for London: {info}. Give a witty 2-sentence analysis.")
            await context.bot.send_message(chat_id=chat_id, text=f"🎩 **Butler's insight:**\n{res.text.strip()}")
        except: pass

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['chat_id'] = update.effective_chat.id
    if client: context.user_data['chat_session'] = client.chats.create(model=MODEL_ID, config={'system_instruction': SYS_INSTR})
    await update.message.reply_text("The Concierge is at your service, Sir. Heathrow manifests are ready.")

async def check_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['chat_id'] = update.effective_chat.id
    await daily_brief(context)

# ─── MAIN ────────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    if not TELEGRAM_TOKEN: exit(1)
    
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    # Ensure a fresh start
    loop = asyncio.get_event_loop()
    loop.run_until_complete(app.bot.delete_webhook(drop_pending_updates=True))

    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('check', check_now))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), chat))

    logger.info("Polling for Sir's requests...")
    app.run_polling(drop_pending_updates=True)
