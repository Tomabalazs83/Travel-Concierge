import os, requests, logging, asyncio, datetime
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import google.generativeai as genai

# ─── CONFIGURATION ───────────────────────────────────────────────────────────────
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_KEY = os.environ.get("GEMINI_KEY")
RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

# ─── AI SETUP ────────────────────────────────────────────────────────────────────
ai_brain = None
try:
    if GEMINI_KEY:
        genai.configure(api_key=GEMINI_KEY)
        ai_brain = genai.GenerativeModel(
            "gemini-2.5-flash",
            system_instruction="You are Jeeves, a dryly witty British butler. Address the user as 'Sir'. Remember past flight details discussed."
        )
except Exception as e:
    logger.error(f"AI setup failed: {e}")

# ─── TRAVEL SEARCH TOOL ──────────────────────────────────────────────────────────
def get_shanghai_travel_info() -> str:
    url = "https://google-flights2.p.rapidapi.com/api/v1/searchFlights"
    params = {
        "departure_id": "AMS", "arrival_id": "PVG", 
        "outbound_date": "2026-07-01", "return_date": "2026-07-10",
        "travel_class": "ECONOMY", "adults": "1", "show_hidden": "1",
        "currency": "EUR", "language_code": "en-US", "country_code": "NL",
        "search_type": "best"
    }
    headers = {"x-rapidapi-key": RAPIDAPI_KEY, "x-rapidapi-host": "google-flights2.p.rapidapi.com"}
    try:
        response = requests.get(url, headers=headers, params=params, timeout=30)
        if response.status_code == 200:
            res_json = response.json()
            flights = res_json.get("data", {}).get("itineraries", {}).get("topFlights", [])
            if not flights: return "The manifest is empty, Sir."
            lead = flights[0]
            price = lead.get('price', '—')
            segments = lead.get('flights', [])
            report = f"💰 **Total Price: €{price} (Round Trip)**\n\n🛫 **OUTBOUND**\n"
            for seg in segments:
                if seg.get('departure_airport', {}).get('airport_code') == "PVG": break
                dep = seg.get('departure_airport', {}).get('airport_code')
                arr = seg.get('arrival_airport', {}).get('airport_code')
                report += f"🔹 {dep} → {arr} ({seg.get('airline')} {seg.get('flight_number')})\n"
            return report
        return "Registry indisposed, Sir."
    except Exception as e:
        return "Manifests obscured, Sir."

# ─── MEMORY HANDLERS ──────────────────────────────────────────────────────────────
async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not ai_brain: return
    user_text = update.message.text.strip()

    # INITIALIZE SESSION IF MISSING (The Memory Source)
    if 'chat_session' not in context.user_data:
        context.user_data['chat_session'] = ai_brain.start_chat(history=[])
        logger.info("New persistent chat session created.")

    try:
        chat_session = context.user_data['chat_session']
        response = chat_session.send_message(user_text)
        await update.message.reply_text(response.text.strip())
    except Exception as e:
        logger.error(f"Chat error: {e}")

async def check_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    info = get_shanghai_travel_info()
    
    # Send flight details to Sir
    await update.message.reply_text(f"🛎 **Registry Update, Sir**\n\n{info}", parse_mode='Markdown')

    # Update AI memory about the latest findings
    if 'chat_session' not in context.user_data:
        context.user_data['chat_session'] = ai_brain.start_chat(history=[])
    
    # We "feed" the data to the AI's memory without Sir seeing the process
    context.user_data['chat_session'].send_message(f"Update your records: I found a flight to Shanghai for €836 via Munich. {info}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Wipe memory for a clean start
    context.user_data['chat_session'] = ai_brain.start_chat(history=[])
    await update.message.reply_text("The Concierge is at your service, Sir. My memory is now a blank ledger, ready for your instructions.")

if __name__ == '__main__':
    if not TELEGRAM_TOKEN: exit(1)
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('check', check_now))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), chat))
    app.run_polling(drop_pending_updates=True)
