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

# ─── THE REGISTRY ENGINE ──────────────────────────────────────────────────────
def call_flight_api(arrival_id, outbound_date, return_date, adults=1, departure_id="AMS"):
    url = "https://google-flights2.p.rapidapi.com/api/v1/searchFlights"
    params = {
        "departure_id": departure_id, "arrival_id": arrival_id,
        "outbound_date": outbound_date, "return_date": return_date,
        "adults": str(adults), "currency": "EUR", "search_type": "best"
    }
    headers = {"x-rapidapi-key": RAPIDAPI_KEY, "x-rapidapi-host": "google-flights2.p.rapidapi.com"}
    
    try:
        logger.info(f"📡 Querying Registry: {departure_id} -> {arrival_id}")
        response = requests.get(url, headers=headers, params=params, timeout=30)
        if response.status_code != 200:
            return f"Error: Registry returned status {response.status_code}"
        
        data = response.json()
        # Navigate the confirmed 2026 schema
        flights = data.get("data", {}).get("itineraries", {}).get("topFlights", [])
        
        if not flights:
            logger.warning(f"Empty results for {arrival_id}. Keys: {list(data.keys())}")
            return "No flights found for these dates in the registry, Sir."

        f = flights[0]
        price = f.get("price", "—")
        legs_text = ""
        for leg in f.get("flights", []):
            legs_text += (f"🔹 {leg.get('departure_airport', {}).get('airport_code')} → "
                         f"{leg.get('arrival_airport', {}).get('airport_code')} | "
                         f"{leg.get('departure_airport', {}).get('time')} | "
                         f"{leg.get('airline')} {leg.get('flight_number')}\n")
        
        return f"Total Price: €{price}\n{legs_text}"
    except Exception as e:
        return f"Technical disturbance: {str(e)}"

# ─── AI SETUP ────────────────────────────────────────────────────────────────────
genai.configure(api_key=GEMINI_KEY)
ai_brain = genai.GenerativeModel(
    model_name="gemini-2.5-flash",
    system_instruction=(
        "You are Jeeves, a British butler and travel agent. Address the user as 'Sir'. "
        "You have access to a flight registry tool. When Sir asks for flights, "
        "respond with the exact phrase 'SEARCH_TRIGGER:DEST:DATE_OUT:DATE_RET:ADULTS'. "
        "Example: 'SEARCH_TRIGGER:PVG:2026-07-01:2026-07-10:1'. "
        "Always use 3-letter IATA codes. Default to AMS departure."
    )
)

# ─── BOT HANDLERS ────────────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['history'] = []
    await update.message.reply_text("The Concierge is at your service, Sir. Our memory is clear and the registry is open.")

async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text.strip()
    if 'history' not in context.user_data: context.user_data['history'] = []
    
    # Initialize chat session with history
    chat_session = ai_brain.start_chat(history=context.user_data['history'])
    
    try:
        response = chat_session.send_message(user_text)
        reply_text = response.text
        
        # Check if the AI wants to trigger a search
        if "SEARCH_TRIGGER" in reply_text:
            parts = reply_text.split(':')
            if len(parts) >= 5:
                dest, d_out, d_ret, adults = parts[1], parts[2], parts[3], parts[4]
                await update.message.reply_text(f"Searching the manifests for {dest}, Sir...")
                
                # Perform the actual tool call
                search_result = call_flight_api(dest, d_out, d_ret, adults)
                
                # Feed the result back into the AI to get a 'Butler' style response
                final_res = chat_session.send_message(f"Registry Result: {search_result}")
                await update.message.reply_text(final_res.text, parse_mode='Markdown')
                context.user_data['history'] = chat_session.history
                return

        await update.message.reply_text(reply_text)
        context.user_data['history'] = chat_session.history
        
    except Exception as e:
        logger.error(f"Chat error: {e}")
        await update.message.reply_text("A momentary lapse in coordination, Sir.")

async def check_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Manual override to force a Shanghai search
    await update.message.reply_text("Consulting the Shanghai manifests immediately, Sir...")
    res = call_flight_api("PVG", "2026-07-01", "2026-07-10")
    await update.message.reply_text(f"🛎 **Registry Update**\n\n{res}", parse_mode='Markdown')

if __name__ == '__main__':
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('check', check_now))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), chat))
    
    logger.info("Jeeves is standing by...")
    app.run_polling(drop_pending_updates=True)
