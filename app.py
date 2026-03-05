import os, requests, datetime, logging
from datetime import datetime as dt, timedelta
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from google import genai # The 2026 Modern SDK

# --- 1. CONFIGURATION ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_KEY = os.environ.get("GEMINI_KEY")
RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

# --- 2. MODERN AI SETUP (SDK v2.0) ---
try:
    # The new SDK uses a Client object instead of global configuration
    client = genai.Client(api_key=GEMINI_KEY)
    MODEL_ID = "gemini-2.5-flash" 
    SYS_INSTR = "You are Jeeves, a sophisticated British butler. Address the user as 'Sir'. Be witty, dry, and concise."
    logger.info("Gemini 2.5 client initialized successfully.")
except Exception as e:
    logger.error(f"AI Setup failed: {e}")
    client = None

# --- 3. FLIGHT TOOL (Simplified for logic check) ---
def get_flight_report(dest_entity):
    # (Your existing Kiwi API logic remains here, returning a string of data)
    return "€126, London, 1h 15m" 

# --- 4. THE CONCIERGE'S EARS (CHAT) ---
async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not client: return
    try:
        # Modern 2026 SDK pattern for generating content
        response = client.models.generate_content(
            model=MODEL_ID,
            config={'system_instruction': SYS_INSTR},
            contents=update.message.text
        )
        await update.message.reply_text(response.text)
    except Exception as e:
        logger.error(f"Chat error: {e}")
        await update.message.reply_text("I'm dreadfully sorry, Sir, my thoughts are a bit muddled.")

# --- 5. THE ANALYTICAL ENGINE (DAILY BRIEF) ---
async def daily_brief(context: ContextTypes.DEFAULT_TYPE):
    chat_id = getattr(context.job, 'chat_id', None) or context.user_data.get('chat_id')
    if not chat_id: return
    
    # ... (Gathering flight data) ...
    data_for_ai = "London: €126, Bali: €587"
    
    # Triggering the analysis with the new SDK
    try:
        analysis_res = client.models.generate_content(
            model=MODEL_ID,
            config={'system_instruction': SYS_INSTR},
            contents=f"Analyze these prices for Sir: {data_for_ai}"
        )
        await context.bot.send_message(chat_id=chat_id, text=f"🎩 **Analysis:**\n{analysis_res.text}")
    except Exception as e:
        logger.error(f"Analysis error: {e}")

# --- 6. LAUNCH ---
if __name__ == '__main__':
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler('check', check_now))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), chat))
    app.run_polling(drop_pending_updates=True)
