import os, requests, logging, asyncio, json
from datetime import datetime
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import google.generativeai as genai
from google.generativeai.types import content_types

# ─── CONFIGURATION ───────────────────────────────────────────────────────────────
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_KEY = os.environ.get("GEMINI_KEY")
RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

# ─── THE TOOL: FLIGHT SEARCH FUNCTION ──────────────────────────────────────────
def search_flights(arrival_id: str, outbound_date: str, return_date: str, adults: int = 1, departure_id: str = "AMS"):
    """
    Searches for real-time flight details. 
    arrival_id and departure_id must be 3-letter IATA codes (e.g., 'PVG', 'JFK', 'LAX').
    Dates must be in 'YYYY-MM-DD' format.
    """
    url = "https://google-flights2.p.rapidapi.com/api/v1/searchFlights"
    querystring = {
        "departure_id": departure_id,
        "arrival_id": arrival_id,
        "outbound_date": outbound_date,
        "return_date": return_date,
        "adults": str(adults),
        "currency": "EUR",
        "search_type": "best"
    }
    headers = {
        "x-rapidapi-key": RAPIDAPI_KEY,
        "x-rapidapi-host": "google-flights2.p.rapidapi.com"
    }

    try:
        response = requests.get(url, headers=headers, params=querystring, timeout=30)
        logger.info(f"API Call: {departure_id}->{arrival_id} | Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            flights = data.get("data", {}).get("itineraries", {}).get("topFlights", [])
            if not flights:
                return {"error": "No flights found for these criteria."}
            
            # Return a structured list of the top 2 options for the AI to summarize
            results = []
            for f in flights[:2]:
                option = {
                    "total_price": f.get("price"),
                    "legs": []
                }
                for leg in f.get("flights", []):
                    option["legs"].append({
                        "from": leg.get("departure_airport", {}).get("airport_code"),
                        "to": leg.get("arrival_airport", {}).get("airport_code"),
                        "departure": leg.get("departure_airport", {}).get("time"),
                        "arrival": leg.get("arrival_airport", {}).get("time"),
                        "airline": leg.get("airline"),
                        "flight_no": leg.get("flight_number"),
                        "aircraft": leg.get("aircraft")
                    })
                results.append(option)
            return {"results": results}
        return {"error": f"API returned status {response.status_code}"}
    except Exception as e:
        return {"error": str(e)}

# ─── AI SETUP WITH TOOLS ────────────────────────────────────────────────────────
genai.configure(api_key=GEMINI_KEY)

# Define the tools available to Jeeves
tools = [search_flights]

ai_brain = genai.GenerativeModel(
    model_name="gemini-2.5-flash",
    tools=tools,
    system_instruction=(
        "You are Jeeves, a sophisticated, dryly witty British butler and expert travel agent. "
        "Address the user as 'Sir'. "
        "You have access to a real-time flight registry tool. "
        "When Sir asks for flights, ALWAYS use the search_flights tool with the correct IATA codes. "
        "Default departure is AMS (Amsterdam) unless stated otherwise. "
        "Current year is 2026. If Sir doesn't provide dates, ask for them politely. "
        "Summarize findings elegantly with flight numbers, times, and aircraft."
    )
)

# ─── BOT HANDLERS ────────────────────────────────────────────────────────────────
async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    user_text = update.message.text.strip()

    if 'chat_session' not in context.user_data:
        # enable_automatic_function_calling=True is the key to autonomy
        context.user_data['chat_session'] = ai_brain.start_chat(history=[], enable_automatic_function_calling=True)

    try:
        chat_session = context.user_data['chat_session']
        response = chat_session.send_message(user_text)
        await update.message.reply_text(response.text, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Chat error: {e}")
        await update.message.reply_text("A momentary lapse in coordination, Sir. Shall we try again?")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['chat_session'] = ai_brain.start_chat(history=[], enable_automatic_function_calling=True)
    await update.message.reply_text("The Concierge is at your service, Sir. I am ready to manage your global itineraries.")

if __name__ == '__main__':
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler('start', start))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), chat))
    
    logger.info("Jeeves is now in the study, awaiting Sir...")
    app.run_polling(drop_pending_updates=True)
