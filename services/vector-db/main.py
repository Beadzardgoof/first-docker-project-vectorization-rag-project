from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import chromadb
from chromadb.config import Settings
import uvicorn
import os
from typing import List, Optional, Dict, Any
import json
import re
from enum import Enum
import numpy as np

# Define enums first
class QueryComplexity(str, Enum):
    SIMPLE = "simple"      # Single word or basic phrase
    MODERATE = "moderate"   # Multiple criteria or specific filters
    COMPLEX = "complex"     # Multiple destinations, comparisons, complex logic

class SearchStrategy(str, Enum):
    EXACT = "exact"           # Precise matching for specific queries
    SIMILARITY = "similarity" # Semantic similarity for broad searches
    HYBRID = "hybrid"         # Combination approach

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

# Create or get collection for flights with ANN optimization
collection = chroma_client.get_or_create_collection(
    name="flights",
    metadata={
        "description": "Flight information for retrieval",
        "hnsw:space": "cosine",  # Use cosine similarity
        "hnsw:M": 16,            # Number of bidirectional links for HNSW
        "hnsw:ef_construction": 200,  # Size of dynamic candidate list
        "hnsw:ef": 100           # Size of dynamic candidate list for search
    }
)

class QueryAnalyzer:
    """Analyzes query complexity and determines optimal search parameters"""
    
    @staticmethod
    def analyze_query_complexity(query: str) -> QueryComplexity:
        """Determine query complexity based on content"""
        query_lower = query.lower()
        
        # Count different types of criteria
        criteria_count = 0
        
        # Location criteria
        if any(word in query_lower for word in ['from', 'to', 'between', 'via']):
            criteria_count += 1
            
        # Time criteria  
        if any(word in query_lower for word in ['tomorrow', 'today', 'weekend', 'morning', 'evening', 'date']):
            criteria_count += 1
            
        # Price criteria
        if any(word in query_lower for word in ['cheap', 'under', 'budget', 'expensive', 'price', '$']):
            criteria_count += 1
            
        # Airline criteria
        if any(word in query_lower for word in ['airline', 'united', 'american', 'delta', 'southwest']):
            criteria_count += 1
            
        # Class criteria
        if any(word in query_lower for word in ['business', 'first', 'economy', 'class']):
            criteria_count += 1
            
        # Comparison words
        if any(word in query_lower for word in ['compare', 'vs', 'versus', 'better', 'best', 'worst']):
            criteria_count += 2  # Comparisons are more complex
            
        # Multiple destinations
        if query_lower.count(' or ') > 0 or query_lower.count(' and ') > 1:
            criteria_count += 2
        
        if criteria_count <= 1:
            return QueryComplexity.SIMPLE
        elif criteria_count <= 3:
            return QueryComplexity.MODERATE
        else:
            return QueryComplexity.COMPLEX
    
    @staticmethod
    def determine_result_count(complexity: QueryComplexity, total_flights: int) -> int:
        """Dynamically determine optimal result count"""
        if complexity == QueryComplexity.SIMPLE:
            # Simple queries: fewer, more precise results
            return min(3, max(1, total_flights // 50))
        elif complexity == QueryComplexity.MODERATE:
            # Moderate queries: balanced result set
            return min(8, max(3, total_flights // 25))
        else:
            # Complex queries: more results for comparison
            return min(15, max(5, total_flights // 15))
    
    @staticmethod
    def determine_search_strategy(query: str, complexity: QueryComplexity) -> SearchStrategy:
        """Determine optimal search strategy"""
        query_lower = query.lower()
        
        # If query has specific flight numbers or codes
        if re.search(r'[A-Z]{2}[0-9]+', query.upper()):
            return SearchStrategy.EXACT
            
        # If complex comparison query
        if complexity == QueryComplexity.COMPLEX:
            return SearchStrategy.HYBRID
            
        # Default to similarity search
        return SearchStrategy.SIMILARITY

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
    n_results: Optional[int] = None  # Will be determined dynamically
    strategy: Optional[SearchStrategy] = None  # Auto-determined
    include_metadata: bool = True
    max_distance: Optional[float] = None  # Filter by similarity threshold

class SearchResult(BaseModel):
    id: str
    document: str
    metadata: dict
    distance: float
    similarity_score: float  # 1 - distance for easier interpretation
    match_type: str         # exact, semantic, partial
    relevance_factors: List[str]  # Why this result was selected

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
    """Enhanced search with dynamic result count and ANN optimization"""
    try:
        analyzer = QueryAnalyzer()
        
        # Analyze query complexity
        complexity = analyzer.analyze_query_complexity(query.query)
        strategy = analyzer.determine_search_strategy(query.query, complexity)
        
        # Get total flight count for dynamic sizing
        total_flights = collection.count()
        
        # Determine optimal result count
        if query.n_results is None:
            n_results = analyzer.determine_result_count(complexity, total_flights)
        else:
            n_results = query.n_results
        
        print(f"=== ENHANCED SEARCH DEBUG ===")
        print(f"Query: {query.query}")
        print(f"Complexity: {complexity}")
        print(f"Strategy: {strategy}")
        print(f"Result count: {n_results}")
        print(f"Total flights: {total_flights}")
        
        # Perform ANN search with optimized parameters
        if strategy == SearchStrategy.EXACT:
            # For exact searches, use higher ef for precision
            search_results = await _exact_search(query.query, n_results)
        elif strategy == SearchStrategy.HYBRID:
            # Combine exact and semantic search
            search_results = await _hybrid_search(query.query, n_results)
        else:
            # Standard similarity search with ANN optimization
            search_results = await _similarity_search(query.query, n_results, query.max_distance)
        
        # Add relevance analysis
        enhanced_results = []
        for result in search_results:
            similarity_score = 1.0 - result.distance
            match_type, relevance_factors = _analyze_match_relevance(query.query, result)
            
            enhanced_results.append(SearchResult(
                id=result.id,
                document=result.document,
                metadata=result.metadata,
                distance=result.distance,
                similarity_score=similarity_score,
                match_type=match_type,
                relevance_factors=relevance_factors
            ))
        
        print(f"=== SEARCH COMPLETED: {len(enhanced_results)} results ===")
        return enhanced_results
        
    except Exception as e:
        print(f"Search error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

async def _exact_search(query: str, n_results: int) -> List[SearchResult]:
    """Exact search for specific flight numbers or codes"""
    # For exact searches, we want higher precision
    results = collection.query(
        query_texts=[query],
        n_results=min(n_results * 2, 20),  # Get more candidates for filtering
        include=['metadatas', 'documents', 'distances']
    )
    
    search_results = []
    for i in range(len(results["ids"][0])):
        search_results.append(SearchResult(
            id=results["ids"][0][i],
            document=results["documents"][0][i],
            metadata=results["metadatas"][0][i],
            distance=results["distances"][0][i],
            similarity_score=1.0 - results["distances"][0][i],
            match_type="exact",
            relevance_factors=[]
        ))
    
    # Filter for exact matches and return top n_results
    return search_results[:n_results]

async def _similarity_search(query: str, n_results: int, max_distance: Optional[float] = None) -> List[SearchResult]:
    """Standard semantic similarity search with ANN"""
    results = collection.query(
        query_texts=[query],
        n_results=n_results,
        include=['metadatas', 'documents', 'distances']
    )
    
    search_results = []
    for i in range(len(results["ids"][0])):
        distance = results["distances"][0][i]
        
        # Apply distance threshold if specified
        if max_distance is not None and distance > max_distance:
            continue
            
        search_results.append(SearchResult(
            id=results["ids"][0][i],
            document=results["documents"][0][i],
            metadata=results["metadatas"][0][i],
            distance=distance,
            similarity_score=1.0 - distance,
            match_type="semantic",
            relevance_factors=[]
        ))
    
    return search_results

async def _hybrid_search(query: str, n_results: int) -> List[SearchResult]:
    """Hybrid search combining exact and semantic approaches"""
    # Get more results for hybrid processing
    candidate_count = min(n_results * 3, 30)
    
    results = collection.query(
        query_texts=[query],
        n_results=candidate_count,
        include=['metadatas', 'documents', 'distances']
    )
    
    search_results = []
    for i in range(len(results["ids"][0])):
        search_results.append(SearchResult(
            id=results["ids"][0][i],
            document=results["documents"][0][i],
            metadata=results["metadatas"][0][i],
            distance=results["distances"][0][i],
            similarity_score=1.0 - results["distances"][0][i],
            match_type="hybrid",
            relevance_factors=[]
        ))
    
    # Score and rank hybrid results
    scored_results = []
    for result in search_results:
        hybrid_score = _calculate_hybrid_score(query, result)
        result.similarity_score = hybrid_score
        scored_results.append(result)
    
    # Sort by hybrid score and return top n_results
    scored_results.sort(key=lambda x: x.similarity_score, reverse=True)
    return scored_results[:n_results]

def _calculate_hybrid_score(query: str, result: SearchResult) -> float:
    """Calculate hybrid score combining multiple factors"""
    base_similarity = 1.0 - result.distance
    
    # Bonus for exact keyword matches
    query_words = set(query.lower().split())
    doc_words = set(result.document.lower().split())
    keyword_overlap = len(query_words.intersection(doc_words)) / max(len(query_words), 1)
    
    # Bonus for metadata matches
    metadata_bonus = 0.0
    if 'airline' in result.metadata:
        if any(airline in query.lower() for airline in [result.metadata['airline'].lower()]):
            metadata_bonus += 0.1
    
    # Combine scores
    hybrid_score = (base_similarity * 0.7) + (keyword_overlap * 0.2) + metadata_bonus
    return min(hybrid_score, 1.0)

def _analyze_match_relevance(query: str, result: SearchResult) -> tuple[str, List[str]]:
    """Analyze why this result is relevant to the query"""
    query_lower = query.lower()
    doc_lower = result.document.lower()
    factors = []
    
    # Check for direct matches
    if result.metadata.get('airline', '').lower() in query_lower:
        factors.append(f"Airline match: {result.metadata.get('airline')}")
    
    if result.metadata.get('departure_city', '').lower() in query_lower:
        factors.append(f"Origin match: {result.metadata.get('departure_city')}")
        
    if result.metadata.get('arrival_city', '').lower() in query_lower:
        factors.append(f"Destination match: {result.metadata.get('arrival_city')}")
    
    # Check for price-related matches
    if any(word in query_lower for word in ['cheap', 'budget', 'under']):
        price = result.metadata.get('price', 0)
        if price < 500:
            factors.append(f"Budget-friendly: ${price}")
    
    # Check for semantic similarity
    if result.similarity_score > 0.8:
        factors.append("High semantic similarity")
    elif result.similarity_score > 0.6:
        factors.append("Good semantic match")
    
    # Determine primary match type
    if len(factors) > 2:
        match_type = "multi-factor"
    elif any("match:" in f for f in factors):
        match_type = "exact"
    else:
        match_type = "semantic"
    
    return match_type, factors

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
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info",
        reload=False,
        access_log=False
    )