#!/usr/bin/env python3
"""
Generate comprehensive mock flight dataset for vector database testing
Creates 100 realistic flights with varied routes, times, and airlines
"""

import json
import random
from datetime import datetime, timedelta
from typing import List, Dict

# Major cities with airport codes
CITIES = [
    {"name": "New York", "code": "NYC", "airports": ["JFK", "LGA", "EWR"]},
    {"name": "Los Angeles", "code": "LAX", "airports": ["LAX", "BUR", "LGB"]},
    {"name": "Chicago", "code": "CHI", "airports": ["ORD", "MDW"]},
    {"name": "Miami", "code": "MIA", "airports": ["MIA", "FLL"]},
    {"name": "San Francisco", "code": "SFO", "airports": ["SFO", "OAK", "SJC"]},
    {"name": "Seattle", "code": "SEA", "airports": ["SEA", "BFI"]},
    {"name": "Boston", "code": "BOS", "airports": ["BOS", "PVD"]},
    {"name": "Denver", "code": "DEN", "airports": ["DEN", "COS"]},
    {"name": "Las Vegas", "code": "LAS", "airports": ["LAS", "VGT"]},
    {"name": "Phoenix", "code": "PHX", "airports": ["PHX", "SDL"]},
    {"name": "Dallas", "code": "DFW", "airports": ["DFW", "DAL"]},
    {"name": "Atlanta", "code": "ATL", "airports": ["ATL", "PDK"]},
    {"name": "Orlando", "code": "MCO", "airports": ["MCO", "SFB"]},
    {"name": "Houston", "code": "HOU", "airports": ["IAH", "HOU"]},
    {"name": "Washington DC", "code": "DCA", "airports": ["DCA", "IAD", "BWI"]},
    {"name": "Paris", "code": "CDG", "airports": ["CDG", "ORY"]},
    {"name": "London", "code": "LHR", "airports": ["LHR", "LGW", "STN"]},
    {"name": "Tokyo", "code": "NRT", "airports": ["NRT", "HND"]},
    {"name": "Frankfurt", "code": "FRA", "airports": ["FRA", "HHN"]},
    {"name": "Amsterdam", "code": "AMS", "airports": ["AMS", "EIN"]},
]

# Airlines with their typical aircraft
AIRLINES = [
    {"name": "American Airlines", "code": "AA", "aircraft": ["Boeing 777", "Boeing 737", "Airbus A321"]},
    {"name": "Delta Air Lines", "code": "DL", "aircraft": ["Airbus A330", "Boeing 757", "Boeing 737"]},
    {"name": "United Airlines", "code": "UA", "aircraft": ["Boeing 787", "Boeing 777", "Airbus A320"]},
    {"name": "Southwest Airlines", "code": "SW", "aircraft": ["Boeing 737", "Boeing 737 MAX"]},
    {"name": "JetBlue Airways", "code": "JB", "aircraft": ["Airbus A320", "Airbus A321", "Embraer E190"]},
    {"name": "Alaska Airlines", "code": "AS", "aircraft": ["Boeing 737", "Airbus A320", "Boeing 737 MAX"]},
    {"name": "Spirit Airlines", "code": "NK", "aircraft": ["Airbus A320", "Airbus A319"]},
    {"name": "Frontier Airlines", "code": "F9", "aircraft": ["Airbus A320", "Airbus A321"]},
    {"name": "Hawaiian Airlines", "code": "HA", "aircraft": ["Airbus A330", "Boeing 717", "Airbus A321"]},
    {"name": "Air France", "code": "AF", "aircraft": ["Boeing 787", "Airbus A350", "Boeing 777"]},
    {"name": "British Airways", "code": "BA", "aircraft": ["Boeing 777", "Airbus A380", "Boeing 787"]},
    {"name": "Lufthansa", "code": "LH", "aircraft": ["Airbus A350", "Boeing 747", "Airbus A320"]},
    {"name": "Emirates", "code": "EK", "aircraft": ["Airbus A380", "Boeing 777", "Boeing 787"]},
    {"name": "KLM", "code": "KL", "aircraft": ["Boeing 777", "Airbus A330", "Boeing 737"]},
    {"name": "Qatar Airways", "code": "QR", "aircraft": ["Airbus A350", "Boeing 777", "Boeing 787"]},
]

def generate_flight_number(airline_code: str, flight_id: int) -> str:
    """Generate realistic flight number"""
    return f"{airline_code}{100 + flight_id}"

def generate_flight_time() -> tuple:
    """Generate departure and arrival times"""
    # Random departure time between 5 AM and 11 PM
    dep_hour = random.randint(5, 23)
    dep_minute = random.choice([0, 15, 30, 45])
    
    # Flight duration between 1-15 hours
    duration_hours = random.randint(1, 15)
    duration_minutes = random.choice([0, 15, 30, 45])
    
    departure = f"{dep_hour:02d}:{dep_minute:02d}"
    
    # Calculate arrival time
    arr_hour = (dep_hour + duration_hours) % 24
    arr_minute = (dep_minute + duration_minutes) % 60
    if dep_minute + duration_minutes >= 60:
        arr_hour = (arr_hour + 1) % 24
    
    arrival = f"{arr_hour:02d}:{arr_minute:02d}"
    
    return departure, arrival

def generate_price(distance_factor: float, airline_name: str) -> float:
    """Generate realistic price based on distance and airline"""
    base_price = 150 + (distance_factor * 300)
    
    # Airline price modifiers
    if "Spirit" in airline_name or "Frontier" in airline_name:
        base_price *= 0.7  # Budget airlines
    elif "Emirates" in airline_name or "Qatar" in airline_name:
        base_price *= 1.8  # Premium airlines
    elif "Southwest" in airline_name or "JetBlue" in airline_name:
        base_price *= 0.85  # Mid-range
    
    # Add random variation
    variation = random.uniform(0.8, 1.3)
    final_price = round(base_price * variation, 2)
    
    return max(99.99, final_price)  # Minimum price

def get_distance_factor(dep_city: str, arr_city: str) -> float:
    """Simple distance estimation for pricing"""
    international_cities = ["Paris", "London", "Tokyo", "Frankfurt", "Amsterdam"]
    
    if dep_city in international_cities or arr_city in international_cities:
        return 2.5  # International flights
    elif abs(hash(dep_city) - hash(arr_city)) % 100 > 70:
        return 1.5  # Cross-country
    else:
        return 1.0  # Regional

def generate_flight_data(num_flights: int = 100) -> List[Dict]:
    """Generate comprehensive flight dataset"""
    flights = []
    
    # Generate dates for the next 30 days
    start_date = datetime.now().date()
    dates = [(start_date + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(30)]
    
    for i in range(num_flights):
        # Select random cities (ensure different departure and arrival)
        departure_city = random.choice(CITIES)
        arrival_city = random.choice([c for c in CITIES if c != departure_city])
        
        # Select airline and aircraft
        airline = random.choice(AIRLINES)
        aircraft = random.choice(airline["aircraft"])
        
        # Generate times and price
        dep_time, arr_time = generate_flight_time()
        distance_factor = get_distance_factor(departure_city["name"], arrival_city["name"])
        price = generate_price(distance_factor, airline["name"])
        
        # Generate available seats (realistic distribution)
        max_seats = {"Boeing 737": 180, "Airbus A320": 180, "Boeing 777": 350, 
                     "Airbus A330": 300, "Boeing 787": 250, "Airbus A350": 300,
                     "Airbus A380": 500, "Boeing 747": 400}.get(aircraft, 180)
        
        available_seats = random.randint(5, min(150, max_seats // 2))
        
        flight = {
            "id": f"flight_{i+1:03d}",
            "flight_number": generate_flight_number(airline["code"], i),
            "airline": airline["name"],
            "departure_city": departure_city["name"],
            "arrival_city": arrival_city["name"],
            "departure_airport": random.choice(departure_city["airports"]),
            "arrival_airport": random.choice(arrival_city["airports"]),
            "departure_time": dep_time,
            "arrival_time": arr_time,
            "date": random.choice(dates),
            "price": price,
            "aircraft_type": aircraft,
            "available_seats": available_seats,
            "duration_estimate": f"{random.randint(1, 15)}h {random.choice([0, 15, 30, 45])}m",
            "class_options": ["Economy", "Premium Economy", "Business", "First"] if price > 800 else ["Economy", "Premium Economy"]
        }
        
        flights.append(flight)
    
    # Sort by price for better organization
    flights.sort(key=lambda x: x["price"])
    
    return flights

def main():
    """Generate and save flight data"""
    print("🛫 Generating comprehensive flight dataset...")
    
    flights = generate_flight_data(100)
    
    # Save to data directory
    output_file = "data/flights_dataset.json"
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(flights, f, indent=2, ensure_ascii=False)
    
    print(f"✅ Generated {len(flights)} flights saved to {output_file}")
    
    # Print some statistics
    airlines = set(flight["airline"] for flight in flights)
    cities = set(flight["departure_city"] for flight in flights) | set(flight["arrival_city"] for flight in flights)
    price_range = (min(flight["price"] for flight in flights), max(flight["price"] for flight in flights))
    
    print(f"\n📊 Dataset Statistics:")
    print(f"   Airlines: {len(airlines)}")
    print(f"   Cities: {len(cities)}")
    print(f"   Price range: ${price_range[0]:.2f} - ${price_range[1]:.2f}")
    print(f"   Date range: {flights[0]['date']} to {max(flight['date'] for flight in flights)}")
    
    # Show sample flights
    print(f"\n✈️ Sample flights:")
    for flight in flights[:3]:
        print(f"   {flight['flight_number']}: {flight['departure_city']} → {flight['arrival_city']} (${flight['price']})")

if __name__ == "__main__":
    main()