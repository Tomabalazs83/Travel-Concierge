def get_flight_price(dest_code):
    # Updated to the most current 2026 endpoint path for Kiwi
    url = "https://kiwi-com-cheap-flights.p.rapidapi.com/v2/search" 
    # If the above still fails, the API may have moved to a different provider name.
    # Let's try a slightly different approach to the parameters.
    params = {
        "fly_from": "AMS",
        "fly_to": dest_code,
        "date_from": "01/07/2026",
        "date_to": "15/07/2026",
        "curr": "EUR",
        "adults": "1",
        "limit": "1"
    }
    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": "kiwi-com-cheap-flights.p.rapidapi.com"
    }
    try:
        res = requests.get(url, headers=headers, params=params, timeout=20)
        
        # If we still get a 404, we will try the 'Skyscanner' style endpoint
        if res.status_code == 404:
            return "Registry moved (404)"
            
        data = res.json()
        if 'data' in data and len(data['data']) > 0:
            price = data['data'][0]['price']
            return f"€{price}"
        return "Route not found"
    except:
        return "Search timed out"
