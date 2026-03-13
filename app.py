import os, requests, logging, asyncio, json
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import google.generativeai as genai

# ─── CONFIGURATION ───────────────────────────────────────────────────────────────
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_KEY = os.environ.get("GEMINI_KEY")
RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

# ─── THE REGISTRY TOOL (Your Exact Approved Logic) ─────────────────────────────
def get_flight_manifest(arrival_id: str, outbound_date: str, return_date: str, adults: str = "1", departure_id: str = "AMS") -> str:
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
        response = requests.get(url, headers=headers, params=params, timeout=45)
        if response.status_code == 200:
            res_json = response.json()
            flights = res_json.get("data", {}).get("itineraries", {}).get("topFlights", [])
            if not flights: return f"The manifests for {arrival_id} are empty for those dates, Sir."
            
            lead = flights[0]
            price = lead.get('price', '—')
            segments = lead.get('flights', [])
            
            report = f"💰 **Total Price: €{price} (Round Trip for {adults})**\n\n🛫 **OUTBOUND JOURNEY**\n"
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
            
            report += f"\n🛬 **RETURN JOURNEY**\n"
            report += f"⚠️ *Return details are bundled in the €{price}.*"
            return report
        return f"The registry responded with status {response.status_code}, Sir."
    except Exception as e:
        return f"I encountered a disturbance in the manifests: {e}, Sir."

# ─── AI SETUP (Gemini 2.5 Flash + JSON Router) ───────────────────────────────
genai.configure(api_key=GEMINI_KEY)

system_prompt = """
You are Jeeves, a dryly witty British butler and expert travel agent. Address the user as 'Sir'. 
Current year is 2026. You remember all conversational context.

CRITICAL DIRECTIVE: If Sir asks to search for flights, or modifies a previous search (e.g., "change the date to July 15", "make it 2 people", "how about Los Angeles instead?"), you MUST output ONLY a JSON object and NO OTHER TEXT.

The JSON MUST be in this exact format:
{"action": "search", "departure_id": "AMS", "arrival_id": "3-letter IATA code", "outbound_date": "YYYY-MM-DD", "return_date": "YYYY-MM-DD", "adults": "1"}

Rules for JSON:
1. Infer missing parameters (like destination or dates) from the chat history.
2. If you lack critical info (like dates or destination) and cannot infer it, DO NOT output JSON. Instead, ask Sir politely in standard text.
3. Default departure is AMS.

If Sir is just chatting or asking a follow-up question that doesn't require a NEW search (e.g., "What was the layover time again?"), respond normally in standard text.
"""

ai_brain = genai.GenerativeModel(
    model_name="gemini-2.5-flash",
    system_instruction=system_prompt
)

# ─── BOT HANDLERS ────────────────────────────────────────────────────────────────
async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    user_text = update.message.text.strip()

    if 'chat_session' not in context.user_data:
        context.user_data['chat_session'] = ai_brain.start_chat(history=[])
        
    chat_session = context.user_data['chat_session']

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')

    try:
        response = await chat_session.send_message_async(user_text)
        reply_text = response.text.strip()

        if '"action"' in reply_text and '"search"' in reply_text:
            clean_json = reply_text.replace('```json', '').replace('```', '').strip()
            
            try:
                params = json.loads(clean_json)
                dest = params.get("arrival_id")
                d_out = params.get("outbound_date")
                d_ret = params.get("return_date")
                adults = str(params.get("adults", "1"))
                dep = params.get("departure_id", "AMS")
                
                wait_msg = await update.message.reply_text(
                    f"Right away, Sir. Consulting the registries for {dest} ({d_out} to {d_ret} for {adults}). This may take a moment..."
                )
                
                loop = asyncio.get_running_loop()
                manifest_report = await loop.run_in_executor(
                    None, get_flight_manifest, dest, d_out, d_ret, adults, dep
                )
                
                await wait_msg.edit_text(f"🛎 **Registry Update**\n\n{manifest_report}", parse_mode='Markdown')
                
                await chat_session.send_message_async(
                    f"System Note: You just executed a search. The results were: {manifest_report}. Keep this in your memory for Sir's future questions."
                )
                return

            except json.JSONDecodeError:
                logger.error("Failed to parse AI JSON command.")
                pass 

        await update.message.reply_text(reply_text)

    except Exception as e:
        logger.error(f"Chat error: {e}")
        await update.message.reply_text("A momentary lapse in my cognitive registers, Sir. The API may be congested.")

# --- RESTORED /CHECK COMMAND ---
async def check_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'chat_session' not in context.user_data:
        context.user_data['chat_session'] = ai_brain.start_chat(history=[])
        
    chat_session = context.user_data['chat_session']
    
    wait_msg = await update.message.reply_text(
        "Right away, Sir. Consulting the Shanghai manifests for July 1st to July 10th. This may take a moment..."
    )
    
    # Run the background search to prevent Telegram freeze
    loop = asyncio.get_running_loop()
    manifest_report = await loop.run_in_executor(
        None, get_flight_manifest, "PVG", "2026-07-01", "2026-07-10", "1", "AMS"
    )
    
    await wait_msg.edit_text(f"🛎 **Registry Update**\n\n{manifest_report}", parse_mode='Markdown')
    
    # Silently feed the exact text to AI memory
    await chat_session.send_message_async(
        f"System Note: You just executed a search. The results were: {manifest_report}. Keep this in your memory for Sir's future questions."
    )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['chat_session'] = ai_brain.start_chat(history=[])
    await update.message.reply_text("The Concierge is at your service, Sir. Memory and Registry are primed for Gemini 2.5 Flash.")

if __name__ == '__main__':
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    loop = asyncio.get_event_loop()
    loop.run_until_complete(app.bot.delete_webhook(drop_pending_updates=True))

    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('check', check_now)) # <--- The Missing Link Restored
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), chat))
    
    logger.info("Jeeves is awaiting Sir's requests...")
    app.run_polling(drop_pending_updates=True)
