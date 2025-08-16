#!/bin/bash

echo "🛫 Starting Flight RAG Microservices"
echo "===================================="

# Check if .env file exists
if [ ! -f .env ]; then
    echo "⚠️  Creating .env file from template..."
    cp .env.example .env
    echo "📝 Please edit .env and add your GEMINI_API_KEY"
    echo "   Then run this script again."
    exit 1
fi

# Check if GEMINI_API_KEY is set
if ! grep -q "GEMINI_API_KEY=your_gemini_api_key_here" .env; then
    echo "✅ GEMINI_API_KEY appears to be configured"
else
    echo "❌ Please set your GEMINI_API_KEY in .env file"
    exit 1
fi

echo "🐳 Starting Docker containers..."
docker-compose up --build -d

echo "⏳ Waiting for services to start..."
sleep 10

echo "🔍 Checking service health..."
echo "Vector DB: http://localhost:8001/health"
echo "LLM Service: http://localhost:8080/health"

echo ""
echo "📊 To seed sample flight data, run:"
echo "   python seed_data.py"
echo ""
echo "💬 To start the console chat, run:"
echo "   docker-compose logs -f console-frontend"
echo ""
echo "🛑 To stop all services:"
echo "   docker-compose down"