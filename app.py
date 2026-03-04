def get_flight_price(dest_entity):
    url = "https://kiwi-com-cheap-flights.p.rapidapi.com/round-trip"
    
    params = {
        "fly_from": "AMS",
        "fly_to": dest_entity,
        "date_from": "01/07/2026",
        "date_to": "15/07/2026",
        "return_from": "20/07/2026",
        "return_to": "05/08/2026",
        "curr": "EUR",
        "adults": 1,
        "max_stopovers": 2,
        "cabin_class": "economy",
        "limit": 1
    }
    
    headers = {
        "x-rapidapi-key": RAPIDAPI_KEY,
        "x-rapidapi-host": "kiwi-com-cheap-flights.p.rapidapi.com"
    }

    try:
        res = requests.get(url, headers=headers, params=params, timeout=20)
        if res.status_code == 200:
            data = res.json()
            # Navigating the new 'itineraries' structure identified in the logs
            itineraries = data.get('itineraries', [])
            if itineraries and len(itineraries) > 0:
                # v1 itineraries usually have a 'price' object with an 'amount'
                price_info = itineraries[0].get('price', {})
                amount = price_info.get('amount')
                return f"€{amount}" if amount else "Price detail missing"
            return "No itineraries found"
        return f"Service Error ({res.status_code})"
    except Exception as e:
        return "Search failed"
