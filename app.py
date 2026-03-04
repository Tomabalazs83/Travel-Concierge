def get_flight_price(dest_code):
    # Updated to v1 and the 'Round trip' endpoint as seen in Sir's image
    url = "https://kiwi-com-cheap-flights.p.rapidapi.com/v1/round-trip"
    
    params = {
        "fly_from": "AMS",
        "fly_to": dest_code,
        "date_from": "01/07/2026",
        "date_to": "15/07/2026",
        "return_from": "16/07/2026", # v1 often requires explicit return dates
        "return_to": "31/07/2026",
        "curr": "EUR",
        "adults": "1"
    }
    
    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": "kiwi-com-cheap-flights.p.rapidapi.com"
    }
    
    try:
        res = requests.get(url, headers=headers, params=params, timeout=20)
        
        if res.status_code != 200:
            return f"Service Issue ({res.status_code})"
            
        data = res.json()
        # v1 data structures can vary; we'll check for the price in the first result
        if 'data' in data and len(data['data']) > 0:
            price = data['data'][0].get('price', 'N/A')
            return f"€{price}"
            
        return "No routes found"
    except Exception as e:
        return f"Request Error"
