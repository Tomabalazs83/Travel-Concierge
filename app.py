import os, requests, logging, asyncio, datetime
from datetime import datetime as dt
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import google.generativeai as genai

# ─── CONFIGURATION ───────────────────────────────────────────────────────────────
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_KEY = os.environ.get("GEMINI_KEY")
RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ─── AI SETUP ────────────────────────────────────────────────────────────────────
ai_brain = None
try:
    if GEMINI_KEY:
        genai.configure(api_key=GEMINI_KEY)
        ai_brain = genai.GenerativeModel(
            "gemini-1.5-flash",
            system_instruction="You are Jeeves, a sophisticated and dryly witty British butler. Always address the user as 'Sir'."
        )
        logger.info("Concierge initialized.")
except Exception as e:
    logger.error(f"AI setup failed: {e}")

# ─── TRAVEL SEARCH TOOL (Shanghai PVG Focus) ───────────────────────────────────
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
        logger.info(f"RapidAPI (PVG): {response.status_code} | Quota: {response.headers.get('X-RateLimit-Requests-Remaining')}")
        
        if response.status_code == 200:
            res_json = response.json()
            flights = res_json.get("data", {}).get("itineraries", {}).get("topFlights", [])
            
            if not flights: return "The Shanghai manifests are empty, Sir."

            lead = flights[0]
            price = lead.get('price', '—')
            segments = lead.get('flights', [])
            
            # Start the report
            report = f"💰 **€{price}**\n"
            
            if len(segments) > 0:
                first_leg = segments[0]
                last_leg = segments[-1]
                
                # Check if the last segment is actually a return (starts at PVG)
                # or just the end of the outbound (ends at PVG)
                dest_reached = last_leg.get('arrival_airport', {}).get('airport_code') == "PVG"
                
                if dest_reached and len(segments) > 1:
                    # This is an outbound journey with layovers
                    report += f"🛫 **Outbound (via {last_leg.get('departure_airport', {}).get('airport_code')}):**\n"
                    report += f"   {first_leg.get('departure_airport', {}).get('time')} ({first_leg.get('airline')})\n"
                    report += f"⚠️ *Note: Return leg details are bundled in the €{price} price but not listed individually, Sir.*"
                elif not dest_reached and len(segments) > 1:
                    # This would be a true round-trip showing both legs
                    report += f"🛫 **Outbound:** {first_leg.get('departure_airport', {}).get('time')}\n"
                    report += f"🛬 **Return:** {last_leg.get('departure_airport', {}).get('time')}"
                else:
                    report += f"🛫 **Outbound:** {lead.get('departure_time')} ({first_leg.get('airline')})"

            return report
            
        return f"Registry error ({response.status_code}), Sir."
    except Exception as e:
        logger.error(f"PVG Error: {e}")
        return "The Shanghai manifests are obscured, Sir."

# ─── BOT HANDLERS ────────────────────────────────────────────────────────────────
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

async def daily_brief(context: ContextTypes.DEFAULT_TYPE):
    chat_id = getattr(context.job, 'chat_id', None) or context.user_data.get('chat_id')
    if not chat_id: return
    
    await context.bot.send_message(chat_id=chat_id, text="Consulting the Shanghai registries for July, Sir...")
    info = get_shanghai_travel_info()
    
    await context.bot.send_message(chat_id=chat_id, text=f"🛎 **Travel Briefing, Sir**\n\n{info}", parse_mode='Markdown')

    if ai_brain:
        try:
            chat_session = context.user_data.get('chat_session') or ai_brain.start_chat(history=[])
            res = chat_session.send_message(f"Sir is considering Shanghai for July. Here is the data: {info}. Give a witty 2-sentence analysis.")
            await context.bot.send_message(chat_id=chat_id, text=f"🎩 **Butler's insight:**\n{res.text.strip()}")
        except: pass

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['chat_id'] = update.effective_chat.id
    if ai_brain: context.user_data['chat_session'] = ai_brain.start_chat(history=[])
    await update.message.reply_text("The Concierge is at your service, Sir. Shanghai manifests are now being monitored.")

async def check_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['chat_id'] = update.effective_chat.id
    await daily_brief(context)

# ─── MAIN ────────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    if not TELEGRAM_TOKEN: exit(1)
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    # Ensure fresh start
    loop = asyncio.get_event_loop()
    loop.run_until_complete(app.bot.delete_webhook(drop_pending_updates=True))

    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('check', check_now))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), chat))

    logger.info("Bot starting...")
    app.run_polling(drop_pending_updates=True)
