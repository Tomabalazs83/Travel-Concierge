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
        logger.info(f"RapidAPI Status: {response.status_code} | Quota: {response.headers.get('X-RateLimit-Requests-Remaining')}")
        
        if response.status_code == 200:
            res_json = response.json()
            data_content = res_json.get("data", {})
            itin_block = data_content.get("itineraries", {})
            
            flights = itin_block.get("topFlights", []) or data_content.get("topFlights", [])
            
            if not flights:
                return "The flight manifest is blank, Sir."

            # The 'lead' is the best round-trip option
            lead = flights[0]
            
            # 1. PRICE: Extracting exactly what the API calls 'price'
            raw_price = lead.get('price')
            price_str = f"€{raw_price}" if raw_price else "Price elusive"

            # 2. FLIGHT SEGMENTS: This is where both Outbound and Return live
            segments = lead.get('flights', [])
            
            # Logic: If it's a direct round trip, segment 0 is out, segment 1 is return.
            # If there are layovers, we need to be more careful.
            if len(segments) >= 2:
                # Identifying outbound (AMS -> LHR) and return (LHR -> AMS)
                out_seg = segments[0]
                ret_seg = segments[-1] # The last segment is usually the final return leg
                
                out_info = f"🛫 **Outbound:** {out_seg.get('departure_airport', {}).get('time', '—')} ({out_seg.get('airline', '—')})"
                ret_info = f"🛬 **Return:** {ret_seg.get('departure_airport', {}).get('time', '—')} ({ret_seg.get('airline', '—')})"
                
                return f"💰 **{price_str}**\n{out_info}\n{ret_info}"
            
            elif len(segments) == 1:
                out_seg = segments[0]
                return f"💰 **{price_str}**\n🛫 **Outbound only:** {out_seg.get('departure_airport', {}).get('time', '—')} ({out_seg.get('airline', '—')})\n(Note: Return details missing from registry, Sir.)"

            return f"💰 **{price_str}**\nDetails are present but structurally complex, Sir."
            
        return f"The registry is indisposed (Status {response.status_code}), Sir."
    except Exception as e:
        logger.error(f"Search error: {e}")
        return "I encountered a disturbance while consulting the manifests, Sir."
