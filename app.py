import os
import http.client
import json
import datetime
import logging
import asyncio
from datetime import datetime as dt, timedelta

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

import google.generativeai as genai

# ─── CONFIGURATION ───────────────────────────────────────────────────────────────
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_KEY     = os.environ.get("GEMINI_KEY")
RAPIDAPI_KEY   = os.environ.get("RAPIDAPI_KEY")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ─── AI SETUP ────────────────────────────────────────────────────────────────────
ai_brain = None
try:
    if not GEMINI_KEY:
        logger.warning("GEMINI_KEY not set → AI disabled")
    else:
        genai.configure(api_key=GEMINI_KEY)
        ai_brain = genai.GenerativeModel(
            "gemini-2.5-flash-lite",
            system_instruction=(
                "You are Jeeves, a sophisticated British butler. "
                "Always address the user as 'Sir'. "
                "Be witty, dry, concise, and elegant in your replies."
            )
        )
        logger.info("Concierge initialized with gemini-2.5-flash-lite")
except Exception as e:
    logger.error(f"AI setup failed: {e}")

# ─── TRAVEL SEARCH TOOL (Booking.com Flights & Hotels) ───────────────────────────
def get_travel_info(dest_entity: str) -> str:
    today = dt.now()
    out_date = (today + timedelta(days=90)).strftime("%Y-%m-%d")
    ret_date = (today + timedelta(days=110)).strftime("%Y-%m-%d")

    # Destination code map (Booking.com uses IATA or city codes)
    dest_map = {
        "City:honolulu_hi_us": "HNL",
        "City:denpasar_id": "DPS",
        "City:london_gb": "LON"
    }
    dest_code = dest_map.get(dest_entity, "XXX")

    conn = http.client.HTTPSConnection("booking-com15.p.rapidapi.com")
    headers = {
        'x-rapidapi-key': RAPIDAPI_KEY,
        'x-rapidapi-host': "booking-com15.p.rapidapi.com"
    }

    flight_info = ""
    hotel_info = ""

    # 1. Round-trip flight search
    try:
        flight_path = f"/api/v1/flights/search-roundtrip?origin=AMS&destination={dest_code}&departureDate={out_date}&returnDate={ret_date}&adults=1&currency=EUR&sort=price"
        conn.request("GET", flight_path, headers=headers)
        res = conn.getresponse()
        data = res.read()
        logger.info(f"Booking.com Flights API status: {res.status}")
        logger.info(f"Flights preview: {data.decode('utf-8')[:500]}...")

        if res.status == 200:
            flight_json = json.loads(data)
            flights = flight_json.get("flights", []) or []
            if flights:
                cheapest = min(flights, key=lambda f: f.get("price", float("inf")))
                price = f"€{cheapest.get('price', '—')}"
                outbound = cheapest.get("outbound", {})
                out_dep = outbound.get("departureTime", "—")
                out_arr = outbound.get("arrivalTime", "—")
                flight_info = f"💰 Flight price: {price}\nOutbound: {out_dep} → {out_arr}"
            else:
                flight_info = "No flights found."
        else:
            flight_info = f"Flight API error ({res.status})."
    except Exception as e:
        logger.error(f"Flight error: {e}")
        flight_info = "Flights elusive, Sir."

    # 2. 4+ star hotel search during stay
    try:
        checkin = out_date
        checkout = ret_date
        hotel_path = f"/api/v1/hotels/search?location={dest_code}&checkin_date={checkin}&checkout_date={checkout}&adults=1&stars=4,5&currency=EUR&sort=price"
        conn.request("GET", hotel_path, headers=headers)
        res = conn.getresponse()
        data = res.read()
        logger.info(f"Booking.com Hotels API status: {res.status}")
        logger.info(f"Hotels preview: {data.decode('utf-8')[:500]}...")

        if res.status == 200:
            hotel_json = json.loads(data)
            hotels = hotel_json.get("hotels", []) or []
            if hotels:
                cheapest = min(hotels, key=lambda h: h.get("price", float("inf")))
                name = cheapest.get("name", "Unknown Hotel")
                address = cheapest.get("address", "Address not provided")
                price = f"€{cheapest.get('price', '—')} for stay"
                hotel_info = f"🏨 Recommended: {name}, {address}, {price}"
            else:
                hotel_info = "No 4+ star hotels found."
        else:
            hotel_info = f"Hotel API error ({res.status})."
    except Exception as e:
        logger.error(f"Hotel error: {e}")
        hotel_info = "Hotels elusive, Sir."

    combined = f"{flight_info}\n\n{hotel_info}" if flight_info or hotel_info else "No travel options found, Sir."
    return combined

# The rest of your code (handlers, main, etc.) remains unchanged
# Replace only the get_cheapest_roundtrip_info with get_travel_info and update daily_brief to use it
async def daily_brief(context: ContextTypes.DEFAULT_TYPE):
    # ... (your existing code)
    for name, entity in options.items():
        info = get_travel_info(entity)  # <-- changed to new function
        report += f"✈️ **{name}**:\n{info}\n\n"
        data_for_ai += f"{name}: {info}. "
    # ... rest unchanged
