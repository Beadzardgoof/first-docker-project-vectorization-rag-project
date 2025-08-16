#!/usr/bin/env python3
"""
Script to seed the vector database with sample flight data
Run this after starting the services to populate the database
"""

import asyncio
import httpx
import json
import os
from typing import List, Dict

# Service URLs
VECTOR_DB_URL = "http://localhost:8001"  # Exposed port for vector-db service
DATA_FILE = "data/sample_flights.json"

async def load_sample_data() -> List[Dict]:
    """Load sample flight data from JSON file"""
    try:
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Error: Could not find {DATA_FILE}")
        return []
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON: {e}")
        return []

async def check_vector_db_health():
    """Check if vector database is accessible"""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{VECTOR_DB_URL}/health")
            return response.status_code == 200
    except Exception as e:
        print(f"Vector DB health check failed: {e}")
        return False

async def seed_flight_data(flights: List[Dict]):
    """Seed the vector database with flight data"""
    print(f"Seeding {len(flights)} flights to vector database...")
    
    success_count = 0
    error_count = 0
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        for flight in flights:
            try:
                response = await client.post(
                    f"{VECTOR_DB_URL}/flights/add",
                    json=flight
                )
                
                if response.status_code == 200:
                    success_count += 1
                    print(f"✅ Added flight {flight['flight_number']}")
                else:
                    error_count += 1
                    print(f"❌ Failed to add flight {flight['flight_number']}: {response.status_code}")
                    
            except Exception as e:
                error_count += 1
                print(f"❌ Error adding flight {flight['flight_number']}: {e}")
    
    print(f"\nSeeding complete:")
    print(f"✅ Successfully added: {success_count} flights")
    print(f"❌ Failed to add: {error_count} flights")
    
    return success_count, error_count

async def get_flight_count():
    """Get current number of flights in database"""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{VECTOR_DB_URL}/flights/count")
            if response.status_code == 200:
                data = response.json()
                return data.get("count", 0)
    except Exception as e:
        print(f"Error getting flight count: {e}")
    return 0

async def main():
    """Main seeding function"""
    print("🛫 Flight Data Seeder")
    print("=" * 40)
    
    # Check if vector database is accessible
    print("Checking vector database connection...")
    if not await check_vector_db_health():
        print("❌ Cannot connect to vector database. Make sure services are running!")
        print("Try: docker-compose up")
        return
    
    print("✅ Vector database is accessible")
    
    # Check current flight count
    current_count = await get_flight_count()
    print(f"Current flights in database: {current_count}")
    
    if current_count > 0:
        choice = input("Database already has flights. Reset and reseed? (y/N): ").strip().lower()
        if choice == 'y':
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.delete(f"{VECTOR_DB_URL}/flights/reset")
                    if response.status_code == 200:
                        print("✅ Database reset successfully")
                    else:
                        print(f"❌ Failed to reset database: {response.status_code}")
                        return
            except Exception as e:
                print(f"❌ Error resetting database: {e}")
                return
        else:
            print("Keeping existing data and adding new flights...")
    
    # Load and seed data
    flights = await load_sample_data()
    if not flights:
        print("❌ No flight data to seed")
        return
    
    success_count, error_count = await seed_flight_data(flights)
    
    # Final count
    final_count = await get_flight_count()
    print(f"\nFinal flights in database: {final_count}")
    
    if success_count > 0:
        print("\n🎉 Data seeding completed! You can now test flight searches.")
        print("\nTry asking the chatbot:")
        print("• 'Find flights from New York to Los Angeles'")
        print("• 'Show me flights to Paris'")
        print("• 'I need a cheap flight to Miami'")

if __name__ == "__main__":
    asyncio.run(main())