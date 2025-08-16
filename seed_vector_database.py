#!/usr/bin/env python3
"""
Enhanced vector database seeding script
Processes flight data into ChromaDB with optimized embeddings and search capabilities
"""

import asyncio
import httpx
import json
import os
import sys
from typing import List, Dict
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.table import Table
from rich.panel import Panel

console = Console()

# Service URLs
VECTOR_DB_URL = "http://localhost:8001"  # Assuming vector-db is exposed for seeding
DATA_FILE = "data/flights_dataset.json"

class FlightProcessor:
    """Processes flight data for optimal vector search"""
    
    def __init__(self):
        self.processed_count = 0
        self.error_count = 0
    
    def create_search_text(self, flight: Dict) -> str:
        """Create comprehensive search text for vector embedding"""
        # Build rich text that includes various search patterns users might use
        search_components = [
            # Basic route information
            f"Flight from {flight['departure_city']} to {flight['arrival_city']}",
            f"{flight['departure_city']} {flight['arrival_city']} route",
            f"{flight['departure_airport']} to {flight['arrival_airport']}",
            
            # Airline and flight details
            f"{flight['airline']} flight {flight['flight_number']}",
            f"{flight['airline']} service",
            f"{flight['aircraft_type']} aircraft",
            
            # Time and date information
            f"Departure {flight['departure_time']} arrival {flight['arrival_time']}",
            f"Flight on {flight['date']}",
            f"Duration approximately {flight.get('duration_estimate', 'N/A')}",
            
            # Price and availability
            f"Price ${flight['price']} per person",
            f"{flight['available_seats']} seats available",
            
            # Common search patterns
            f"cheap flights {flight['departure_city']} {flight['arrival_city']}",
            f"direct flight {flight['departure_city']} to {flight['arrival_city']}",
            f"book flight {flight['departure_city']} {flight['arrival_city']}",
            
            # International vs domestic
            self._get_route_type(flight),
            
            # Class options
            f"Available classes: {', '.join(flight.get('class_options', ['Economy']))}",
        ]
        
        return " | ".join(search_components)
    
    def _get_route_type(self, flight: Dict) -> str:
        """Determine if flight is domestic or international"""
        international_cities = [
            "Paris", "London", "Tokyo", "Frankfurt", "Amsterdam",
            "Dubai", "Madrid", "Rome", "Barcelona", "Munich"
        ]
        
        dep_international = flight['departure_city'] in international_cities
        arr_international = flight['arrival_city'] in international_cities
        
        if dep_international or arr_international:
            return "international flight"
        else:
            return "domestic flight"
    
    def create_metadata(self, flight: Dict) -> Dict:
        """Create structured metadata for filtering and display"""
        return {
            "flight_number": flight["flight_number"],
            "airline": flight["airline"],
            "departure_city": flight["departure_city"],
            "arrival_city": flight["arrival_city"],
            "departure_airport": flight.get("departure_airport", ""),
            "arrival_airport": flight.get("arrival_airport", ""),
            "departure_time": flight["departure_time"],
            "arrival_time": flight["arrival_time"],
            "date": flight["date"],
            "price": flight["price"],
            "aircraft_type": flight["aircraft_type"],
            "available_seats": flight["available_seats"],
            "duration": flight.get("duration_estimate", ""),
            "route_type": self._get_route_type(flight),
            "class_options": ", ".join(flight.get("class_options", ["Economy"])),
            "price_category": self._categorize_price(flight["price"])
        }
    
    def _categorize_price(self, price: float) -> str:
        """Categorize price for filtering"""
        if price < 200:
            return "budget"
        elif price < 500:
            return "economy"
        elif price < 1000:
            return "premium"
        else:
            return "luxury"

async def load_flight_data() -> List[Dict]:
    """Load flight data from JSON file"""
    try:
        if not os.path.exists(DATA_FILE):
            console.print(f"[red]❌ Flight data file not found: {DATA_FILE}[/red]")
            console.print("[yellow]💡 Run 'python generate_flight_data.py' first[/yellow]")
            return []
        
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            flights = json.load(f)
        
        console.print(f"[green]✅ Loaded {len(flights)} flights from {DATA_FILE}[/green]")
        return flights
        
    except json.JSONDecodeError as e:
        console.print(f"[red]❌ Error parsing JSON: {e}[/red]")
        return []
    except Exception as e:
        console.print(f"[red]❌ Error loading flight data: {e}[/red]")
        return []

async def check_vector_db_health() -> bool:
    """Check if vector database is accessible"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{VECTOR_DB_URL}/health")
            return response.status_code == 200
    except Exception as e:
        console.print(f"[red]❌ Vector DB health check failed: {e}[/red]")
        return False

async def clear_existing_data() -> bool:
    """Clear existing flight data"""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.delete(f"{VECTOR_DB_URL}/flights/reset")
            return response.status_code == 200
    except Exception as e:
        console.print(f"[red]❌ Error clearing database: {e}[/red]")
        return False

async def seed_flight_to_vector_db(flight: Dict, processor: FlightProcessor) -> bool:
    """Seed individual flight to vector database"""
    try:
        # Create optimized search text and metadata
        search_text = processor.create_search_text(flight)
        metadata = processor.create_metadata(flight)
        
        # Prepare flight data for vector DB
        flight_data = {
            "id": flight["id"],
            "flight_number": flight["flight_number"],
            "airline": flight["airline"],
            "departure_city": flight["departure_city"],
            "arrival_city": flight["arrival_city"],
            "departure_time": flight["departure_time"],
            "arrival_time": flight["arrival_time"],
            "date": flight["date"],
            "price": flight["price"],
            "aircraft_type": flight["aircraft_type"],
            "available_seats": flight["available_seats"]
        }
        
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                f"{VECTOR_DB_URL}/flights/add",
                json=flight_data
            )
            
            if response.status_code == 200:
                processor.processed_count += 1
                return True
            else:
                processor.error_count += 1
                console.print(f"[yellow]⚠️ Failed to add {flight['flight_number']}: HTTP {response.status_code}[/yellow]")
                return False
                
    except Exception as e:
        processor.error_count += 1
        console.print(f"[red]❌ Error adding flight {flight.get('flight_number', 'unknown')}: {e}[/red]")
        return False

async def get_final_count() -> int:
    """Get final count of flights in database"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{VECTOR_DB_URL}/flights/count")
            if response.status_code == 200:
                data = response.json()
                return data.get("count", 0)
    except Exception:
        pass
    return 0

async def test_search_functionality(processor: FlightProcessor) -> None:
    """Test the vector search with sample queries"""
    test_queries = [
        "flights from New York to Los Angeles",
        "cheap flights to Paris",
        "American Airlines flights",
        "flights under $300",
        "international flights"
    ]
    
    console.print("\n[cyan]🔍 Testing search functionality...[/cyan]")
    
    for query in test_queries:
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(
                    f"{VECTOR_DB_URL}/flights/search",
                    json={"query": query, "n_results": 3}
                )
                
                if response.status_code == 200:
                    results = response.json()
                    console.print(f"[green]✅ '{query}' → {len(results)} results[/green]")
                else:
                    console.print(f"[yellow]⚠️ '{query}' → HTTP {response.status_code}[/yellow]")
                    
        except Exception as e:
            console.print(f"[red]❌ Search test failed for '{query}': {e}[/red]")

async def main():
    """Main seeding function"""
    # Display welcome
    welcome_panel = Panel(
        "[bold cyan]🛫 Vector Database Flight Seeder[/bold cyan]\n\n"
        "This script will:\n"
        "• Load comprehensive flight dataset\n"
        "• Process flights for optimal vector search\n"
        "• Seed ChromaDB with searchable flight data\n"
        "• Test search functionality",
        title="Flight Data Processor",
        border_style="cyan"
    )
    console.print(welcome_panel)
    
    # Check if vector database is accessible
    console.print("\n[yellow]🔍 Checking vector database connection...[/yellow]")
    if not await check_vector_db_health():
        console.print("[red]❌ Cannot connect to vector database![/red]")
        console.print("[yellow]💡 Make sure services are running: docker-compose up -d[/yellow]")
        return
    
    console.print("[green]✅ Vector database is accessible[/green]")
    
    # Load flight data
    flights = await load_flight_data()
    if not flights:
        return
    
    # Ask to clear existing data
    current_count = await get_final_count()
    if current_count > 0:
        console.print(f"\n[yellow]⚠️ Database currently has {current_count} flights[/yellow]")
        clear_db = console.input("Clear existing data and reseed? [y/N]: ").strip().lower()
        if clear_db == 'y':
            console.print("[yellow]🗑️ Clearing existing data...[/yellow]")
            if await clear_existing_data():
                console.print("[green]✅ Database cleared[/green]")
            else:
                console.print("[red]❌ Failed to clear database[/red]")
                return
        else:
            console.print("[blue]ℹ️ Adding to existing data...[/blue]")
    
    # Initialize processor
    processor = FlightProcessor()
    
    # Seed flights with progress bar
    console.print(f"\n[cyan]📊 Seeding {len(flights)} flights to vector database...[/cyan]")
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console
    ) as progress:
        
        task = progress.add_task("Processing flights...", total=len(flights))
        
        for flight in flights:
            await seed_flight_to_vector_db(flight, processor)
            progress.update(task, advance=1)
    
    # Display results
    final_count = await get_final_count()
    
    results_table = Table(title="Seeding Results", border_style="green")
    results_table.add_column("Metric", style="cyan", no_wrap=True)
    results_table.add_column("Value", style="white")
    
    results_table.add_row("✅ Successfully processed", str(processor.processed_count))
    results_table.add_row("❌ Failed to process", str(processor.error_count))
    results_table.add_row("📊 Total flights in DB", str(final_count))
    results_table.add_row("🎯 Success rate", f"{(processor.processed_count / len(flights) * 100):.1f}%")
    
    console.print(results_table)
    
    if processor.processed_count > 0:
        # Test search functionality
        await test_search_functionality(processor)
        
        console.print("\n[green]🎉 Vector database seeding completed![/green]")
        console.print("\n[blue]💡 You can now test flight searches with queries like:[/blue]")
        console.print("   • 'Find flights from New York to Los Angeles'")
        console.print("   • 'Show me cheap flights to Europe'")
        console.print("   • 'I need a flight under $500'")
    else:
        console.print("\n[red]❌ No flights were successfully processed![/red]")

if __name__ == "__main__":
    asyncio.run(main())