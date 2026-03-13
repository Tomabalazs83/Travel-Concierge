import os, requests, logging, asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import google.generativeai as genai

# ─── CONFIGURATION ───────────────────────────────────────────────────────────────
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_KEY = os.environ.get("GEMINI_KEY")
RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

# ─── THE REGISTRY TOOL (Your Working Search Logic) ─────────────────────────────
def get_flight_manifest(arrival_id: str, outbound_date: str, return_date: str, adults: int = 1, departure_id: str = "AMS") -> str:
    """
    Queries the flight registry. Use 3-letter IATA codes (e.g., PVG, JFK).
    Dates must be YYYY-MM-DD.
    """
    url = "https://google-flights2.p.rapidapi.com/api/v1/searchFlights"
    params = {
        "departure_id": departure_id, "arrival_id": arrival_id,
        "outbound_date": outbound_date, "return_date": return_date,
        "travel_class": "ECONOMY", "adults": str(adults), "show_hidden": "1",
        "currency": "EUR", "language_code": "en-US", "country_code": "NL",
        "search_type": "best"
    }
    headers = {"x-rapidapi-key": RAPIDAPI_KEY, "x-rapidapi-host": "google-flights2.p.rapidapi.com"}
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=30)
        if response.status_code == 200:
            res_json = response.json()
            flights = res_json.get("data", {}).get("itineraries", {}).get("topFlights", [])
            if not flights: return f"The manifests for {arrival_id} are empty, Sir."
            
            lead = flights[0]
            price = lead.get('price', '—')
            segments = lead.get('flights', [])
            
            report = f"💰 **Total Price: €{price} (Round Trip)**\n\n🛫 **OUTBOUND JOURNEY**\n"
            for seg in segments:
                if seg.get('departure_airport', {}).get('airport_code') == arrival_id: break
                airline = seg.get('airline', 'Unknown')
                f_num = seg.get('flight_number', '—')
                dep_ap = seg.get('departure_airport', {}).get('airport_code', '—')
                arr_ap = seg.get('arrival_airport', {}).get('airport_code', '—')
                dep_time = seg.get('departure_airport', {}).get('time', '—')
                arr_time = seg.get('arrival_airport', {}).get('time', '—')
                aircraft = seg.get('aircraft', 'Standard Aircraft')
                
                report += f"🔹 **{dep_ap} → {arr_ap}**\n"
                report += f"   Depart: {dep_time}\n"
                report += f"   Arrive: {arr_time}\n"
                report += f"   Flight: {airline} {f_num} ({aircraft})\n"
            
            report += f"\n🛬 **RETURN JOURNEY ({return_date})**\n"
            report += f"⚠️ *Return details are bundled in the €{price}.*"
            return report
        return f"The registry responded with status {response.status_code}, Sir."
    except Exception as e:
        return f"I encountered a disturbance in the manifests: {e}, Sir."

# ─── AI SETUP (Gemini 2.5 Flash + Automatic Tool Use) ────────────────────────
genai.configure(api_key=GEMINI_KEY)

ai_brain = genai.GenerativeModel(
    model_name="gemini-2.5-flash",
    tools=[get_flight_manifest],
    system_instruction=(
        "You are Jeeves, a dryly witty British butler and expert travel agent. "
        "Address the user as 'Sir'. Current year is 2026. "
        "You have access to the get_flight_manifest tool. "
        "When Sir asks for flights, use the tool. If Sir is vague, ask for dates or destinations. "
        "Default departure is AMS. Remember previous flight details to allow for comparisons."
    )
)

# ─── BOT HANDLERS ────────────────────────────────────────────────────────────────
async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    user_text = update.message.text.strip()

    if 'chat_session' not in context.user_data:
        context.user_data['chat_session'] = ai_brain.start_chat(history=[], enable_automatic_function_calling=True)

    try:
        # Automatic function calling handles the tool execution and result summary
        response = context.user_data['chat_session'].send_message(user_text)
        await update.message.reply_text(response.text.strip(), parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Chat error: {e}")
        await update.message.reply_text("A momentary lapse in my cognitive registers, Sir. Perhaps we should /start again?")

async def check_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Force a search for Shanghai to keep the tradition alive."""
    await update.message.reply_text("Consulting the Shanghai manifests for July, Sir...")
    # Re-route through chat so the result is stored in memory
    update.message.text = "Search flights to Shanghai (PVG) from July 1 to July 10, 2026."
    await chat(update, context)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['chat_session'] = ai_brain.start_chat(history=[], enable_automatic_function_calling=True)
    await update.message.reply_text("The Concierge is at your service, Sir. Memory and Registry are primed.")

if __name__ == '__main__':
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    loop = asyncio.get_event_loop()
    loop.run_until_complete(app.bot.delete_webhook(drop_pending_updates=True))

    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('check', check_now))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), chat))
    
    logger.info("Jeeves is awaiting Sir's requests...")
    app.run_polling(drop_pending_updates=True)
