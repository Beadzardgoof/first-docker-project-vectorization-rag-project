from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import httpx
import uvicorn
import os
from typing import List, Optional, Dict, Any
from datetime import datetime
import asyncio
import json

app = FastAPI(title="Flight RAG Service", version="1.0.0")

# Vector DB connection
VECTOR_DB_URL = os.getenv("VECTOR_DB_URL", "http://vector-db:8000")

class NumericalFilters(BaseModel):
    """Numerical criteria for filtering flight results"""
    max_price: Optional[float] = None
    min_price: Optional[float] = None
    max_duration_hours: Optional[float] = None
    min_available_seats: Optional[int] = None
    departure_after: Optional[str] = None    # "08:00", "12:30"
    departure_before: Optional[str] = None   # "18:00", "23:59"
    arrival_after: Optional[str] = None
    arrival_before: Optional[str] = None

class FlightSearchRequest(BaseModel):
    query: str
    max_results: int = 5
    numerical_filters: Optional[NumericalFilters] = None

class FlightSearchResponse(BaseModel):
    flights: List[Dict[str, Any]]
    total_found: int

class FlightData(BaseModel):
    flight_number: str
    airline: str
    departure_city: str
    arrival_city: str
    departure_time: str
    arrival_time: str
    date: str
    price: float
    aircraft_type: str
    available_seats: int

def apply_numerical_filters(flights: List[Dict[str, Any]], filters: NumericalFilters) -> List[Dict[str, Any]]:
    """
    Filter flight results based on numerical criteria.
    Returns flights that match ALL specified criteria.
    """
    filtered_flights = []
    
    for flight in flights:
        # Skip flights that don't have required metadata
        if not flight:
            continue
            
        # Price filtering
        if filters.max_price is not None:
            flight_price = flight.get('price')
            if flight_price is None or flight_price > filters.max_price:
                continue
                
        if filters.min_price is not None:
            flight_price = flight.get('price')
            if flight_price is None or flight_price < filters.min_price:
                continue
        
        # Available seats filtering
        if filters.min_available_seats is not None:
            available_seats = flight.get('available_seats')
            if available_seats is None or available_seats < filters.min_available_seats:
                continue
        
        # Time-based filtering (departure/arrival times)
        if filters.departure_after or filters.departure_before:
            departure_time = flight.get('departure_time')
            if departure_time and not passes_time_filter(departure_time, filters.departure_after, filters.departure_before):
                continue
                
        if filters.arrival_after or filters.arrival_before:
            arrival_time = flight.get('arrival_time')
            if arrival_time and not passes_time_filter(arrival_time, filters.arrival_after, filters.arrival_before):
                continue
        
        # Duration filtering (if we can calculate it)
        if filters.max_duration_hours is not None:
            duration = calculate_flight_duration(flight.get('departure_time'), flight.get('arrival_time'))
            if duration is not None and duration > filters.max_duration_hours:
                continue
        
        # Flight passes all filters
        filtered_flights.append(flight)
    
    return filtered_flights

def passes_time_filter(flight_time: str, after_time: Optional[str], before_time: Optional[str]) -> bool:
    """
    Check if flight time passes the time range filters.
    Times are in "HH:MM" format (24-hour).
    """
    try:
        # Parse flight time (assume format like "14:30" or "2:30 PM")
        flight_hour, flight_minute = parse_time_string(flight_time)
        if flight_hour is None:
            return True  # Can't parse, so don't filter out
            
        flight_minutes = flight_hour * 60 + flight_minute
        
        # Check after time constraint
        if after_time:
            after_hour, after_minute = parse_time_string(after_time)
            if after_hour is not None:
                after_minutes = after_hour * 60 + after_minute
                if flight_minutes < after_minutes:
                    return False
        
        # Check before time constraint  
        if before_time:
            before_hour, before_minute = parse_time_string(before_time)
            if before_hour is not None:
                before_minutes = before_hour * 60 + before_minute
                if flight_minutes > before_minutes:
                    return False
        
        return True
        
    except Exception:
        # If we can't parse times, don't filter out the flight
        return True

def parse_time_string(time_str: str) -> tuple[Optional[int], Optional[int]]:
    """
    Parse various time formats to extract hour and minute.
    Supports: "14:30", "2:30 PM", "14:30:00", etc.
    """
    try:
        time_str = time_str.strip()
        
        # Handle AM/PM format
        is_pm = 'PM' in time_str.upper()
        is_am = 'AM' in time_str.upper()
        time_str = time_str.replace('AM', '').replace('PM', '').replace('am', '').replace('pm', '').strip()
        
        # Split by colon and take first two parts
        parts = time_str.split(':')
        if len(parts) >= 2:
            hour = int(parts[0])
            minute = int(parts[1])
            
            # Convert 12-hour to 24-hour format
            if is_pm and hour != 12:
                hour += 12
            elif is_am and hour == 12:
                hour = 0
                
            return hour, minute
        
        return None, None
        
    except (ValueError, IndexError):
        return None, None

def calculate_flight_duration(departure_time: str, arrival_time: str) -> Optional[float]:
    """
    Calculate flight duration in hours from departure and arrival times.
    Assumes same-day flights for simplicity.
    """
    try:
        dep_hour, dep_minute = parse_time_string(departure_time)
        arr_hour, arr_minute = parse_time_string(arrival_time)
        
        if dep_hour is None or arr_hour is None:
            return None
            
        dep_minutes = dep_hour * 60 + dep_minute
        arr_minutes = arr_hour * 60 + arr_minute
        
        # Handle overnight flights (arrival next day)
        if arr_minutes < dep_minutes:
            arr_minutes += 24 * 60
            
        duration_minutes = arr_minutes - dep_minutes
        return duration_minutes / 60.0
        
    except Exception:
        return None

# FastAPI endpoints for flight search

# FastAPI endpoints for health checks and direct access
@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "rag-service"}

@app.post("/search", response_model=FlightSearchResponse)
async def search_flights_direct(request: FlightSearchRequest):
    """Enhanced REST endpoint with dynamic result count and ANN optimization"""
    try:
        # Let vector DB determine optimal result count if not specified
        search_payload = {"query": request.query}
        if request.max_results > 0:
            search_payload["n_results"] = request.max_results
        
        print(f"RAG Service: Searching with payload: {search_payload}")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{VECTOR_DB_URL}/flights/search",
                json=search_payload
            )
            response.raise_for_status()
            search_results = response.json()
        
        print(f"RAG Service: Received {len(search_results)} results from vector DB")
        
        flights = []
        for result in search_results:
            # Include additional metadata from enhanced search
            flight_data = result["metadata"].copy()
            flight_data["search_metadata"] = {
                "similarity_score": result.get("similarity_score", 0.0),
                "match_type": result.get("match_type", "unknown"),
                "relevance_factors": result.get("relevance_factors", []),
                "distance": result.get("distance", 1.0)
            }
            flights.append(flight_data)
        
        # Apply post-search filtering based on numerical criteria
        if request.numerical_filters:
            filtered_flights = apply_numerical_filters(flights, request.numerical_filters)
        else:
            filtered_flights = flights
        
        return FlightSearchResponse(
            flights=filtered_flights,
            total_found=len(flights)
        )
    except Exception as e:
        print(f"RAG Service error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/vector-db/status")
async def check_vector_db_status():
    """Check if vector database is accessible"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{VECTOR_DB_URL}/health")
            response.raise_for_status()
            return {"vector_db_status": "connected", "details": response.json()}
    except Exception as e:
        return {"vector_db_status": "disconnected", "error": str(e)}

@app.on_event("startup")
async def startup_event():
    """Startup event for RAG service"""
    print("Starting RAG service...")
    print("RAG service started successfully")

if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info",
        reload=False,
        workers=1,  # Single worker for MCP server
        access_log=False
    )