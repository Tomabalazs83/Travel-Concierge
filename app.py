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

# --- AI SETUP (Fixing the 404/v1beta issue) ---
ai_brain = None
try:
    if GEMINI_KEY:
        genai.configure(api_key=GEMINI_KEY)
        # Explicitly using 'gemini-1.5-flash' which is the stable production name
        ai_brain = genai.GenerativeModel(
            model_name="gemini-2.5-flash",
            system_instruction="You are Jeeves, a sophisticated British butler. Always address the user as 'Sir'. You remember all flight details shared in this chat history."
        )
        logger.info("Concierge Brain online.")
except Exception as e:
    logger.error(f"AI setup failed: {e}")

# --- TRAVEL SEARCH TOOL (Restored to Full Detail) ---
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
            if not flights: return "The manifests are empty, Sir."
            
            lead = flights[0]
            price = lead.get('price', '—')
            segments = lead.get('flights', [])
            
            report = f"💰 **Total Price: €{price} (Round Trip)**\n\n🛫 **OUTBOUND JOURNEY**\n"
            
            for seg in segments:
                # If the segment starts at PVG, we've reached the destination (Return handled separately)
                if seg.get('departure_airport', {}).get('airport_code') == "PVG": break
                
                airline = seg.get('airline', 'Unknown')
                f_num = seg.get('flight_number', '—')
                dep_ap = seg.get('departure_airport', {}).get('airport_code', '—')
                arr_ap = seg.get('arrival_airport', {}).get('airport_code', '—')
                dep_time = seg.get('departure_airport', {}).get('time', '—')
                aircraft = seg.get('aircraft', 'Standard Aircraft')
                
                report += f"🔹 **{dep_ap} → {arr_ap}**\n"
                report += f"   Time: {dep_time}\n"
                report += f"   Flight: {airline} {f_num} ({aircraft})\n"
            
            report += f"\n🛬 **RETURN JOURNEY (July 10)**\n"
            report += f"⚠️ *Return details are bundled in the €{price}, but specific numbers require token validation.*"
            return report
        return "Registry indisposed, Sir."
    except Exception as e:
        return f"Manifests obscured: {e}, Sir."

# --- BOT HANDLERS ---
async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not ai_brain: return
    user_text = update.message.text.strip()

    # Get or create persistent session for memory
    if 'chat_session' not in context.user_data:
        context.user_data['chat_session'] = ai_brain.start_chat(history=[])

    try:
        response = context.user_data['chat_session'].send_message(user_text)
        await update.message.reply_text(response.text.strip())
    except Exception as e:
        logger.error(f"Chat error: {e}")
        await update.message.reply_text("My thoughts are currently a bit scattered, Sir. Perhaps we should /start anew?")

async def check_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Consulting the Shanghai registries for July, Sir...")
    info = get_shanghai_travel_info()
    
    # Send detailed results to Sir
    await update.message.reply_text(f"🛎 **Registry Update**\n\n{info}", parse_mode='Markdown')

    # Update AI memory about the latest findings (Silently adding context to the history)
    if 'chat_session' not in context.user_data:
        context.user_data['chat_session'] = ai_brain.start_chat(history=[])
    
    # We send the data to the history so Jeeves "knows" it for future questions
    context.user_data['chat_session'].history.append({"role": "user", "parts": [f"System Update: You found these flights for Sir: {info}"]})
    context.user_data['chat_session'].history.append({"role": "model", "parts": ["Understood, Sir. I have recorded these Shanghai flight details in my ledger."]})

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Wipe memory for a clean start
    context.user_data['chat_session'] = ai_brain.start_chat(history=[])
    await update.message.reply_text("The Concierge is at your service, Sir. I have cleared my ledger for your new requests.")

if __name__ == '__main__':
    if not TELEGRAM_TOKEN: exit(1)
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    # Webhook cleanup for fresh Railway start
    loop = asyncio.get_event_loop()
    loop.run_until_complete(app.bot.delete_webhook(drop_pending_updates=True))

    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('check', check_now))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), chat))
    
    logger.info("Polling for Sir's requests...")
    app.run_polling(drop_pending_updates=True)
