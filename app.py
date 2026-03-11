import os, requests, logging, asyncio, datetime
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import google.generativeai as genai

# --- CONFIGURATION ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_KEY = os.environ.get("GEMINI_KEY")
RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

# --- AI SETUP ---
ai_brain = None
try:
    if GEMINI_KEY:
        genai.configure(api_key=GEMINI_KEY)
        ai_brain = genai.GenerativeModel(
            "gemini-1.5-flash",
            system_instruction="You are Jeeves, a dryly witty British butler. Address the user as 'Sir'. You remember all flight details shared in this chat."
        )
        logger.info("Concierge Brain online.")
except Exception as e:
    logger.error(f"AI setup failed: {e}")

# --- TRAVEL SEARCH TOOL ---
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
        logger.info(f"RapidAPI (PVG): {response.status_code}")
        
        if response.status_code == 200:
            res_json = response.json()
            flights = res_json.get("data", {}).get("itineraries", {}).get("topFlights", [])
            if not flights: return "Registry is blank, Sir."
            
            lead = flights[0]
            price = lead.get('price', '—')
            segments = lead.get('flights', [])
            
            report = f"💰 **Total Price: €{price} (Round Trip)**\n\n🛫 **OUTBOUND**\n"
            for seg in segments:
                if seg.get('departure_airport', {}).get('airport_code') == "PVG": break
                dep = seg.get('departure_airport', {}).get('airport_code')
                arr = seg.get('arrival_airport', {}).get('airport_code')
                airline = seg.get('airline', 'Unknown')
                f_num = seg.get('flight_number', '—')
                report += f"🔹 {dep} → {arr} ({airline} {f_num})\n"
            
            report += f"\n🛬 **RETURN JOURNEY (July 10)**\nDetails bundled in total price."
            return report
        return f"The registry is indisposed (Status {response.status_code}), Sir."
    except Exception as e:
        logger.error(f"Search Error: {e}")
        return "I encountered a disturbance in the manifests, Sir."

# --- BOT HANDLERS ---
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

async def check_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # 1. TRIGGER LIVE SEARCH (The part that was missing in your logs)
    await update.message.reply_text("Consulting the Shanghai registries for July, Sir...")
    info = get_shanghai_travel_info()
    
    # 2. SEND RESULTS TO SIR
    await update.message.reply_text(f"🛎 **Registry Update**\n\n{info}", parse_mode='Markdown')

    # 3. FEED THE AI MEMORY (SILENTLY)
    if 'chat_session' not in context.user_data:
        context.user_data['chat_session'] = ai_brain.start_chat(history=[])
    
    context.user_data['chat_session'].send_message(
        f"Internal Butler Memo: I just found this flight for Sir: {info}. Please remember these details for future questions."
    )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['chat_session'] = ai_brain.start_chat(history=[])
    await update.message.reply_text("Concierge at your service, Sir. Memory initialized.")

if __name__ == '__main__':
    if not TELEGRAM_TOKEN: exit(1)
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    # Ensure fresh start for Railway
    loop = asyncio.get_event_loop()
    loop.run_until_complete(app.bot.delete_webhook(drop_pending_updates=True))

    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('check', check_now))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), chat))
    
    logger.info("Polling for Sir's requests...")
    app.run_polling(drop_pending_updates=True)
