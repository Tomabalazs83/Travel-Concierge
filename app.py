def get_london_travel_info() -> str:
    outbound_date, return_date = "2026-07-01", "2026-07-10"
    url = "https://google-flights2.p.rapidapi.com/api/v1/searchFlights"
    params = {
        "departure_id": "AMS", "arrival_id": "LHR",
        "outbound_date": outbound_date, "return_date": return_date,
        "travel_class": "ECONOMY", "adults": "1", "currency": "EUR",
        "language_code": "en-US", "country_code": "NL"
    }
    headers = {"x-rapidapi-key": RAPIDAPI_KEY, "x-rapidapi-host": "google-flights2.p.rapidapi.com"}

    try:
        response = requests.get(url, headers=headers, params=params, timeout=30)
        remaining = response.headers.get('X-RateLimit-Requests-Remaining', 'N/A')
        logger.info(f"RapidAPI Status: {response.status_code} | Quota: {remaining}")
        
        if response.status_code == 200:
            res_json = response.json()
            data_content = res_json.get("data", {})
            itin_block = data_content.get("itineraries", {})
            
            # Navigate the hierarchy we confirmed in previous logs
            flights = itin_block.get("topFlights", []) or data_content.get("topFlights", []) or \
                      itin_block.get("otherFlights", []) or data_content.get("otherFlights", [])
            
            if not flights:
                return "The flight manifest is currently blank, Sir."

            lead = flights[0]
            
            # --- ROBUST PRICE EXTRACTION ---
            # We look for 'price' as a direct value, then inside objects
            price_data = lead.get('price')
            if isinstance(price_data, dict):
                price = price_data.get('raw') or price_data.get('amount') or price_data.get('formatted')
            else:
                price = price_data

            # If the extraction resulted in €201 and we suspect it's a default, 
            # let's log the lead keys for Sir's inspection.
            logger.info(f"Extracted Price: {price} | Lead Keys: {list(lead.keys())}")
            
            dep_time = lead.get('departure_time', '—')
            arr_time = lead.get('arrival_time', '—')
            
            segments = lead.get('flights', [])
            airline = segments[0].get('airline', 'Unknown Carrier') if segments else "Carrier Unknown"
            
            return f"💰 **€{price}**\n🛫 Outbound: {dep_time}\n🛬 Arrival: {arr_time}\n✈️ {airline}"
            
        return f"The registry is indisposed (Status {response.status_code}), Sir."
    except Exception as e:
        logger.error(f"Flight search error: {e}")
        return "I encountered a disturbance while consulting the manifests, Sir."
