import os, requests, logging, asyncio, json
from datetime import datetime
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import google.generativeai as genai

# ─── CONFIGURATION ───────────────────────────────────────────────────────────────
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_KEY = os.environ.get("GEMINI_KEY")
RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ─── THE TOOL: FLIGHT SEARCH FUNCTION ──────────────────────────────────────────
def search_flights(arrival_id: str, outbound_date: str, return_date: str, adults: int = 1, departure_id: str = "AMS"):
    """
    Searches for real-time flight details using IATA codes and YYYY-MM-DD dates.
    """
    url = "https://google-flights2.p.rapidapi.com/api/v1/searchFlights"
    querystring = {
        "departure_id": departure_id,
        "arrival_id": arrival_id,
        "outbound_date": outbound_date,
        "return_date": return_date,
        "adults": str(adults),
        "currency": "EUR",
        "language_code": "en-US",
        "country_code": "NL",
        "search_type": "best"
    }
    headers = {
        "x-rapidapi-key": RAPIDAPI_KEY,
        "x-rapidapi-host": "google-flights2.p.rapidapi.com"
    }

    try:
        logger.info(f"🔍 Butler Tool Triggered: {departure_id} -> {arrival_id} ({outbound_date})")
        response = requests.get(url, headers=headers, params=querystring, timeout=30)
        
        if response.status_code != 200:
            logger.error(f"❌ API Error: {response.status_code} - {response.text}")
            return {"error": f"The registry is currently locked (Status {response.status_code})."}

        data = response.json()
        itin = data.get("data", {}).get("itineraries", {})
        flights = itin.get("topFlights", []) or itin.get("otherFlights", [])

        if not flights:
            logger.warning(f"⚠️ No flights found for {arrival_id} on {outbound_date}")
            return {"error": "No flights found in the manifest for these specific parameters."}
        
        # Capture the top option with full detail
        f = flights[0]
        result = {
            "total_price": f.get("price"),
            "legs": []
        }
        for leg in f.get("flights", []):
            result["legs"].append({
                "from": leg.get("departure_airport", {}).get("airport_code"),
                "to": leg.get("arrival_airport", {}).get("airport_code"),
                "departure": leg.get("departure_airport", {}).get("time"),
                "arrival": leg.get("arrival_airport", {}).get("time"),
                "airline": leg.get("airline"),
                "flight_no": leg.get("flight_number"),
                "aircraft": leg.get("aircraft")
            })
        
        logger.info(f"✅ Flight Found: €{result['total_price']}")
        return result

    except Exception as e:
        logger.error(f"💥 Tool Crash: {str(e)}")
        return {"error": f"A disturbance in the force: {str(e)}"}

# ─── AI SETUP ────────────────────────────────────────────────────────────────────
genai.configure(api_key=GEMINI_KEY)

ai_brain = genai.GenerativeModel(
    model_name="gemini-1.5-flash",
    tools=[search_flights],
    system_instruction=(
        "You are Jeeves, a sophisticated British butler and master travel agent. "
        "Address the user as 'Sir'. Current year is 2026. "
        "When Sir mentions a destination and dates, you MUST use the search_flights tool. "
        "Always default departure to AMS unless told otherwise. "
        "If the tool returns an error, explain it dryly to Sir. "
        "Summarize flights with prices, flight numbers, aircraft, and EXACT times."
    )
)

# ─── BOT HANDLERS ────────────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['chat_session'] = ai_brain.start_chat(history=[], enable_automatic_function_calling=True)
    await update.message.reply_text("The Concierge is at your service, Sir. I have my ledger and my tools ready.")

async def check_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manually trigger the Shanghai search via the AI to keep memory in sync."""
    await update.message.reply_text("Certainly, Sir. Consulting the Shanghai manifests for July 1st...")
    
    if 'chat_session' not in context.user_data:
        context.user_data['chat_session'] = ai_brain.start_chat(history=[], enable_automatic_function_calling=True)
    
    # We force the AI to 'think' about the search so it stays in its memory
    response = context.user_data['chat_session'].send_message(
        "Please check flights to Shanghai (PVG) from Amsterdam (AMS) for July 1 to July 10, 2026, for 1 person."
    )
    await update.message.reply_text(response.text, parse_mode='Markdown')

async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    user_text = update.message.text.strip()

    if 'chat_session' not in context.user_data:
        context.user_data['chat_session'] = ai_brain.start_chat(history=[], enable_automatic_function_calling=True)

    try:
        # Automatic function calling handles the search_flights tool
        response = context.user_data['chat_session'].send_message(user_text)
        await update.message.reply_text(response.text, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Chat error: {e}")
        await update.message.reply_text("I'm dreadfully sorry, Sir, but my analytical engine has stalled.")

if __name__ == '__main__':
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    # Cleaning webhooks for fresh polling
    loop = asyncio.get_event_loop()
    loop.run_until_complete(app.bot.delete_webhook(drop_pending_updates=True))

    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('check', check_now))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), chat))
    
    logger.info("Jeeves is now standing by in the study...")
    app.run_polling(drop_pending_updates=True)
