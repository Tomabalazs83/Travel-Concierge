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

# ─── THE REGISTRY ENGINE (Restored to Full Detail) ─────────────────────────────
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
            return f"Error: Registry status {response.status_code}"
        
        data = response.json()
        flights = data.get("data", {}).get("itineraries", {}).get("topFlights", [])
        
        if not flights:
            return "No flights found in the manifest, Sir."

        f = flights[0]
        price = f.get("price", "—")
        segments = f.get("flights", [])
        
        # Build the detailed report that Jeeves will use and remember
        report = f"💰 **Total Price: €{price} (Round Trip)**\n\n"
        for i, leg in enumerate(segments):
            # Identify if it's the outbound or return leg
            is_return = leg.get('departure_airport', {}).get('airport_code') == arrival_id
            icon = "🔸" if is_return else "🔹"
            
            dep_ap = leg.get('departure_airport', {}).get('airport_code', '—')
            arr_ap = leg.get('arrival_airport', {}).get('airport_code', '—')
            dep_t = leg.get('departure_airport', {}).get('time', '—')
            arr_t = leg.get('arrival_airport', {}).get('time', '—')
            airline = leg.get('airline', 'Unknown')
            f_num = leg.get('flight_number', '—')
            aircraft = leg.get('aircraft', 'Standard Aircraft')

            report += f"{icon} **{dep_ap} → {arr_ap}**\n"
            report += f"   Depart: {dep_t}\n"
            report += f"   Arrive: {arr_t}\n"
            report += f"   Flight: {airline} {f_num} ({aircraft})\n\n"
        
        return report
    except Exception as e:
        return f"Technical disturbance: {str(e)}"

# ─── AI SETUP (Now using Gemini 2.5 Flash as requested) ──────────────────────
genai.configure(api_key=GEMINI_KEY)
ai_brain = genai.GenerativeModel(
    model_name="gemini-2.5-flash",
    system_instruction=(
        "You are Jeeves, a British butler and expert travel concierge. Address the user as 'Sir'. "
        "You have access to a flight registry. When Sir asks for flights, "
        "YOU MUST respond with this exact trigger: SEARCH_TRIGGER:DEST:DATE_OUT:DATE_RET:ADULTS. "
        "Once search results are provided to you, summarize them with wit and absolute detail. "
        "Always remember the flight details discussed in previous turns."
    )
)

# ─── BOT HANDLERS ────────────────────────────────────────────────────────────────
async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text.strip()
    if 'history' not in context.user_data: context.user_data['history'] = []
    
    chat_session = ai_brain.start_chat(history=context.user_data['history'])
    
    try:
        response = chat_session.send_message(user_text)
        reply_text = response.text
        
        if "SEARCH_TRIGGER" in reply_text:
            parts = reply_text.split(':')
            if len(parts) >= 5:
                dest, d_out, d_ret, adults = parts[1], parts[2], parts[3], parts[4]
                await update.message.reply_text(f"Searching for {dest}, Sir...")
                
                search_result = call_flight_api(dest, d_out, d_ret, adults)
                
                # CRITICAL: We feed the result back into the same chat session history
                final_res = chat_session.send_message(f"System: Search successful. Results: {search_result}")
                await update.message.reply_text(final_res.text, parse_mode='Markdown')
                
                # Save the history including the search results
                context.user_data['history'] = chat_session.history
                return

        await update.message.reply_text(reply_text)
        context.user_data['history'] = chat_session.history
        
    except Exception as e:
        logger.error(f"Chat error: {e}")
        await update.message.reply_text("A momentary lapse in coordination, Sir.")

async def check_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Initiating full manifest check, Sir...")
    # Using the trigger method even for /check to ensure it hits memory
    await chat(update, context) # Re-routes to chat logic for Shanghai (assuming that's the context)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['history'] = []
    await update.message.reply_text("Concierge at your service, Sir. Memory and Registry are primed for Gemini 2.5 Flash.")

if __name__ == '__main__':
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('check', check_now))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), chat))
    app.run_polling(drop_pending_updates=True)
