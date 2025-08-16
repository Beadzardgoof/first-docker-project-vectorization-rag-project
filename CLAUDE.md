# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a complete microservices architecture for flight search using RAG (Retrieval-Augmented Generation). The system combines:
- **Vector Database**: ChromaDB for semantic flight search
- **RAG Service**: Processes queries and retrieves relevant flights  
- **LLM Service**: Google Gemini 1.5 Flash for natural language responses
- **Console Frontend**: Rich-based interactive chat interface
- **Docker**: Full containerization with service orchestration

## Architecture

```
Console Frontend → LLM Service → RAG Service → Vector Database
    (Rich CLI)      (Gemini)     (FastAPI)     (ChromaDB)
        ↓               ↓            ↓             ↓
    User Input →   AI Response → Flight Search → Vector Storage
```

**Service Communication:**
- **HTTP**: Console ↔ LLM, RAG ↔ Vector DB
- **Internal Docker Network**: All inter-service communication
- **External Access**: Only LLM service exposed on port 8080

## Development Commands

### Quick Start
```bash
# 1. Configure API key
cp .env.example .env
# Edit .env and add your GEMINI_API_KEY

# 2. Start all services
docker-compose up --build

# 3. Seed sample flight data
python seed_data.py

# 4. Start chat interface
docker-compose exec console-frontend python main.py
```

### Individual Service Commands
```bash
# Build and run specific service
docker-compose up vector-db
docker-compose up rag-service  
docker-compose up llm-service

# View logs
docker-compose logs -f [service-name]

# Stop all services
docker-compose down
```

### Development Testing
```bash
# Test vector database directly
curl http://localhost:8001/health
curl http://localhost:8001/flights/count

# Test LLM service
curl http://localhost:8080/health
curl -X POST http://localhost:8080/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Find flights from NYC to LAX"}'
```

## Service Details

### Vector Database Service (Port 8001)
- **FastAPI + ChromaDB**
- **Endpoints**: `/flights/add`, `/flights/search`, `/flights/count`
- **Purpose**: Stores flight data as vectors for semantic search

### RAG Service (Internal only)
- **FastAPI with MCP server capability**
- **Endpoints**: `/search`, `/health`
- **Purpose**: Processes natural language queries and retrieves flights

### LLM Service (Port 8080)
- **FastAPI + Google Gemini**
- **Endpoints**: `/chat`, `/health`, `/rag-service/status`
- **Purpose**: Provides conversational AI with flight search integration

### Console Frontend (Interactive)
- **Rich library for beautiful CLI**
- **Features**: Health checks, retry logic, formatted responses
- **Commands**: `help`, `status`, `clear`, `quit`

## Configuration

### Environment Variables
- `GEMINI_API_KEY`: Required for Google Gemini API access
- `VECTOR_DB_URL`: Internal service URL (default: http://vector-db:8000)
- `RAG_SERVICE_URL`: Internal service URL (default: http://rag-service:8000)

### Data Management
- **Sample Data**: `data/sample_flights.json` contains 10 sample flights
- **Seeding**: Use `python seed_data.py` to populate the database
- **Reset**: DELETE `/flights/reset` endpoint clears all data

## Troubleshooting

### Common Issues
1. **Services not starting**: Check Docker daemon and port conflicts
2. **API key errors**: Verify GEMINI_API_KEY in .env file
3. **No flight results**: Run `python seed_data.py` to add sample data
4. **Connection errors**: Wait for services to fully start (10-15 seconds)

### Health Checks
```bash
# Check all services
curl http://localhost:8080/health
curl http://localhost:8080/rag-service/status

# Check Docker containers
docker-compose ps
```

## Learning Notes

This project demonstrates:
- **Microservices Architecture**: Service separation and communication
- **Docker Orchestration**: Multi-container application deployment
- **Vector Search**: Semantic similarity for flight matching
- **API Integration**: External LLM service integration
- **Error Handling**: Graceful degradation and retry logic
- **User Experience**: Rich CLI with status indicators and help