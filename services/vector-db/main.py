from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import chromadb
from chromadb.config import Settings
import uvicorn
import os
from typing import List, Optional
import json

app = FastAPI(title="Flight Vector Database Service", version="1.0.0")

# Initialize ChromaDB client
chroma_client = chromadb.PersistentClient(
    path="/app/data",
    settings=Settings(
        chroma_server_host="0.0.0.0",
        chroma_server_http_port=8000,
        allow_reset=True
    )
)

# Create or get collection for flights
collection = chroma_client.get_or_create_collection(
    name="flights",
    metadata={"description": "Flight information for retrieval"}
)

class FlightDocument(BaseModel):
    id: str
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

class SearchQuery(BaseModel):
    query: str
    n_results: int = 5

class SearchResult(BaseModel):
    id: str
    document: str
    metadata: dict
    distance: float

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "vector-db"}

@app.get("/api/v1/heartbeat")
async def heartbeat():
    """Health check endpoint for Docker Compose"""
    return {"status": "ok"}

@app.post("/flights/add")
async def add_flight(flight: FlightDocument):
    """Add a flight document to the vector database"""
    try:
        # Create document text for embedding
        document_text = f"""Flight {flight.flight_number} by {flight.airline}
        From: {flight.departure_city} at {flight.departure_time}
        To: {flight.arrival_city} at {flight.arrival_time}
        Date: {flight.date}
        Price: ${flight.price}
        Aircraft: {flight.aircraft_type}
        Available seats: {flight.available_seats}"""
        
        collection.add(
            documents=[document_text],
            metadatas=[flight.dict()],
            ids=[flight.id]
        )
        
        return {"message": "Flight added successfully", "id": flight.id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/flights/search", response_model=List[SearchResult])
async def search_flights(query: SearchQuery):
    """Search for flights using vector similarity"""
    try:
        results = collection.query(
            query_texts=[query.query],
            n_results=query.n_results
        )
        
        search_results = []
        for i in range(len(results["ids"][0])):
            search_results.append(SearchResult(
                id=results["ids"][0][i],
                document=results["documents"][0][i],
                metadata=results["metadatas"][0][i],
                distance=results["distances"][0][i]
            ))
        
        return search_results
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/flights/count")
async def get_flight_count():
    """Get the total number of flights in the database"""
    try:
        count = collection.count()
        return {"count": count}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/flights/reset")
async def reset_database():
    """Reset the entire flight database (use with caution)"""
    try:
        chroma_client.reset()
        global collection
        collection = chroma_client.get_or_create_collection(
            name="flights",
            metadata={"description": "Flight information for retrieval"}
        )
        return {"message": "Database reset successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    # TODO(human): Configure server settings
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )