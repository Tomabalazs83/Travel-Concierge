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
ai_brain = genai.GenerativeModel(
    model_name="gemini-1.5-flash",
    system_instruction="You are Jeeves, a dryly witty British butler. Address the user as 'Sir'. You help manage travel manifests."
)
genai.configure(api_key=GEMINI_KEY)

# --- THE UNIVERSAL SEARCH TOOL ---
def get_travel_info(dest_code: str) -> str:
    url = "https://google-flights2.p.rapidapi.com/api/v1/searchFlights"
    params = {
        "departure_id": "AMS", "arrival_id": dest_code, 
        "outbound_date": "2026-07-01", "return_date": "2026-07-10",
        "travel_class": "ECONOMY", "adults": "1", "currency": "EUR",
        "language_code": "en-US", "country_code": "NL", "search_type": "best"
    }
    headers = {"x-rapidapi-key": RAPIDAPI_KEY, "x-rapidapi-host": "google-flights2.p.rapidapi.com"}
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=30)
        logger.info(f"RapidAPI ({dest_code}): {response.status_code}")
        
        if response.status_code == 200:
            res_json = response.json()
            flights = res_json.get("data", {}).get("itineraries", {}).get("topFlights", [])
            if not flights: return f"The manifests for {dest_code} are currently blank, Sir."
            
            lead = flights[0]
            price = lead.get('price', '—')
            segments = lead.get('flights', [])
            
            report = f"💰 **Total Price: €{price} (Round Trip)**\n\n🛫 **OUTBOUND**\n"
            for seg in segments:
                if seg.get('departure_airport', {}).get('airport_code') == dest_code: break
                dep = seg.get('departure_airport', {}).get('airport_code', '—')
                arr = seg.get('arrival_airport', {}).get('airport_code', '—')
                report += f"🔹 {dep} → {arr} ({seg.get('airline')} {seg.get('flight_number')})\n"
            
            return report
        return "The registry is indisposed, Sir."
    except Exception as e:
        return f"Disturbance in the manifests: {e}"

# --- UPDATED CHAT HANDLER WITH "INTENT DETECTION" ---
async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not GEMINI_KEY: return
    user_text = update.message.text.strip()
    
    if 'chat_session' not in context.user_data:
        context.user_data['chat_session'] = ai_brain.start_chat(history=[])

    # TRIGGER: If Sir mentions a new city, we force a registry search
    if "new york" in user_text.lower():
        await update.message.reply_text("Searching the New York manifests, Sir...")
        info = get_travel_info("JFK")
        context.user_data['chat_session'].history.append({"role": "user", "parts": [f"System: Found JFK flights: {info}"]})
        await update.message.reply_text(info, parse_mode='Markdown')
        return

    try:
        response = context.user_data['chat_session'].send_message(user_text)
        await update.message.reply_text(response.text.strip())
    except Exception as e:
        logger.error(f"Chat error: {e}")

async def check_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Defaulting back to Shanghai for the standard check
    await update.message.reply_text("Consulting the Shanghai registries, Sir...")
    info = get_travel_info("PVG")
    await update.message.reply_text(f"🛎 **Update**\n\n{info}", parse_mode='Markdown')

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['chat_session'] = ai_brain.start_chat(history=[])
    await update.message.reply_text("The Concierge is at your service, Sir. Memory and Registry are aligned.")

if __name__ == '__main__':
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('check', check_now))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), chat))
    app.run_polling(drop_pending_updates=True)
