from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from openai import OpenAI
import uvicorn
import os
from typing import List, Optional
import json
import asyncio
import httpx
from dotenv import load_dotenv
from intent_detector import create_intent_detector, IntentDetectionResult, SearchParameters, FlightIntentType
from datetime import datetime, timedelta
from collections import defaultdict
import time

app = FastAPI(title="Flight LLM Service", version="1.0.0")

# Load environment variables
load_dotenv()

# Configure OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY environment variable is required")

# Initialize OpenAI client
openai_client = OpenAI(api_key=OPENAI_API_KEY)

# Initialize Intent Detector (avoid name collision with module)
detector = create_intent_detector(OPENAI_API_KEY)

# RAG service URL
RAG_SERVICE_URL = os.getenv("RAG_SERVICE_URL", "http://rag-service:8000")

class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = None

class ChatResponse(BaseModel):
    response: str
    conversation_id: str
    used_flight_search: bool = False
    detected_intent: Optional[str] = None
    intent_confidence: Optional[float] = None
    search_parameters: Optional[dict] = None

class ConversationMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str
    timestamp: datetime = datetime.now()
    metadata: Optional[dict] = None

class PricingManager:
    """Manages OpenAI pricing with caching"""
    
    def __init__(self):
        self.pricing_cache = {
            "gpt-4o-mini": {
                "input_cost_per_1k": 0.00015,
                "output_cost_per_1k": 0.0006
            }
        }
        self.last_updated = datetime.now()
        self.cache_duration = timedelta(hours=6)
    
    async def get_current_pricing(self, model: str = "gpt-4o-mini") -> dict:
        """Get current pricing with fallback"""
        try:
            # Try to fetch updated pricing (simplified for now)
            if datetime.now() - self.last_updated > self.cache_duration:
                await self._update_pricing()
            return self.pricing_cache.get(model, self.pricing_cache["gpt-4o-mini"])
        except Exception:
            return self.pricing_cache["gpt-4o-mini"]
    
    async def _update_pricing(self):
        """Update pricing from API (placeholder for real implementation)"""
        # For now, keep hardcoded rates - you can enhance this later
        self.last_updated = datetime.now()

class CondensationCostCalculator:
    """Calculates the cost-benefit analysis for conversation condensation"""
    
    def __init__(self, pricing_manager: PricingManager):
        self.pricing_manager = pricing_manager
        # Empirically tested ratios
        self.compression_ratio = 0.2  # Summary is ~20% of original
        self.prompt_overhead = 150    # Extra tokens for summarization prompt
    
    async def calculate_condensation_economics(self, conversation_tokens: int) -> dict:
        """Calculate if condensation is economically beneficial"""
        pricing = await self.pricing_manager.get_current_pricing()
        
        # Cost of using full conversation in future requests
        full_context_cost_per_request = (conversation_tokens / 1000) * pricing["input_cost_per_1k"]
        
        # One-time cost to create condensed version
        condensation_input_tokens = conversation_tokens + self.prompt_overhead
        condensation_output_tokens = conversation_tokens * self.compression_ratio
        
        condensation_cost = (
            (condensation_input_tokens / 1000) * pricing["input_cost_per_1k"] +
            (condensation_output_tokens / 1000) * pricing["output_cost_per_1k"]
        )
        
        # Cost of using condensed conversation in future requests
        condensed_tokens = condensation_output_tokens + 100  # system prompt
        condensed_cost_per_request = (condensed_tokens / 1000) * pricing["input_cost_per_1k"]
        
        # Calculate break-even point
        savings_per_request = full_context_cost_per_request - condensed_cost_per_request
        break_even_requests = condensation_cost / savings_per_request if savings_per_request > 0 else float('inf')
        
        return {
            "should_condense": break_even_requests <= 3.0,  # Profitable within 3 requests
            "break_even_requests": break_even_requests,
            "condensation_cost": condensation_cost,
            "savings_per_request": savings_per_request,
            "full_context_cost_per_request": full_context_cost_per_request,
            "condensed_context_cost_per_request": condensed_cost_per_request,
            "estimated_condensed_tokens": int(condensed_tokens)
        }

class ConversationManager:
    """Manages conversation history and context optimization"""
    
    def __init__(self, max_tokens: int = 15000):
        self.conversations: Dict[str, List[ConversationMessage]] = defaultdict(list)
        self.max_tokens = max_tokens
        self.pricing_manager = PricingManager()
        self.cost_calculator = CondensationCostCalculator(self.pricing_manager)
    
    def add_message(self, conversation_id: str, role: str, content: str, metadata: dict = None):
        """Add a message to conversation history"""
        message = ConversationMessage(
            role=role,
            content=content,
            metadata=metadata or {}
        )
        self.conversations[conversation_id].append(message)
    
    def estimate_tokens(self, text: str) -> int:
        """Rough token estimation: ~4 characters per token for English"""
        return len(text) // 4
    
    def get_conversation_tokens(self, conversation_id: str) -> int:
        """Calculate total tokens in conversation"""
        messages = self.conversations[conversation_id]
        total_tokens = 0
        for msg in messages:
            total_tokens += self.estimate_tokens(msg.content)
        return total_tokens
    
    
    async def should_condense_context(self, conversation_id: str) -> bool:
        """Smart cost-based decision for context management"""
        messages = self.conversations[conversation_id]
        conversation_tokens = self.get_conversation_tokens(conversation_id)
        
        # Always keep short conversations full
        if conversation_tokens < 2000 or len(messages) < 4:
            return False
        
        # Always condense extremely long conversations
        if conversation_tokens > self.max_tokens:
            return True
        
        # For medium conversations, use cost-benefit analysis
        try:
            economics = await self.cost_calculator.calculate_condensation_economics(conversation_tokens)
            
            # Additional heuristics for better decision making
            recent_activity = self._is_conversation_active(conversation_id)
            conversation_depth = len(messages)
            
            # More likely to condense if:
            # 1. Economics favor it (break-even <= 3 requests)
            # 2. Conversation is active (likely to continue)
            # 3. Conversation has depth (many exchanges)
            should_condense = (
                economics["should_condense"] and 
                (recent_activity or conversation_depth > 8)
            )
            
            print(f"=== CONDENSATION DECISION ===\n"
                  f"Tokens: {conversation_tokens}\n"
                  f"Break-even: {economics['break_even_requests']:.1f} requests\n"
                  f"Cost to condense: ${economics['condensation_cost']:.6f}\n"
                  f"Savings per request: ${economics['savings_per_request']:.6f}\n"
                  f"Active conversation: {recent_activity}\n"
                  f"Decision: {'CONDENSE' if should_condense else 'KEEP_FULL'}\n"
                  f"=============================")
            
            return should_condense
            
        except Exception as e:
            print(f"Error in condensation decision: {e}")
            # Fallback to simple token threshold
            return conversation_tokens > 8000
    
    def _is_conversation_active(self, conversation_id: str) -> bool:
        """Determine if conversation is likely to continue"""
        messages = self.conversations[conversation_id]
        if not messages:
            return False
        
        # Check if last message was recent (within 10 minutes)
        last_message_time = messages[-1].timestamp
        time_since_last = datetime.now() - last_message_time
        
        return time_since_last < timedelta(minutes=10)
    
    async def get_context_messages(self, conversation_id: str, system_prompt: str) -> List[dict]:
        """Get optimized context for LLM based on conversation state"""
        messages = self.conversations[conversation_id]
        
        if await self.should_condense_context(conversation_id):
            return await self._get_condensed_context(conversation_id, system_prompt)
        else:
            return self._get_full_context(conversation_id, system_prompt)
    
    def _get_full_context(self, conversation_id: str, system_prompt: str) -> List[dict]:
        """Return full conversation context"""
        context = [{"role": "system", "content": system_prompt}]
        for msg in self.conversations[conversation_id]:
            context.append({"role": msg.role, "content": msg.content})
        return context
    
    async def _get_condensed_context(self, conversation_id: str, system_prompt: str) -> List[dict]:
        """Return condensed conversation context with smart summarization"""
        messages = self.conversations[conversation_id]
        
        # Keep last 3 exchanges (6 messages) as full context
        recent_messages = messages[-6:] if len(messages) > 6 else messages
        older_messages = messages[:-6] if len(messages) > 6 else []
        
        # Create intelligent summary of older context
        if older_messages:
            context_summary = self._create_conversation_summary(older_messages)
            enhanced_prompt = f"{system_prompt}\n\nPrevious Conversation Summary: {context_summary}"
        else:
            enhanced_prompt = system_prompt
        
        context = [{"role": "system", "content": enhanced_prompt}]
        for msg in recent_messages:
            context.append({"role": msg.role, "content": msg.content})
        
        return context
    
    def _create_conversation_summary(self, messages: List[ConversationMessage]) -> str:
        """Create an intelligent summary of conversation history"""
        # Extract key information from older messages
        user_queries = []
        preferences = []
        search_criteria = []
        
        for msg in messages:
            if msg.role == "user":
                content = msg.content.lower()
                # Extract flight preferences
                if any(word in content for word in ["cheap", "budget", "affordable"]):
                    preferences.append("budget-conscious")
                if any(word in content for word in ["business", "first", "premium"]):
                    preferences.append("premium class")
                if any(airline in content for airline in ["united", "american", "delta"]):
                    for airline in ["united", "american", "delta"]:
                        if airline in content:
                            preferences.append(f"{airline} airlines")
                            break
                
                # Extract destinations mentioned
                cities = ["paris", "london", "tokyo", "new york", "los angeles", "miami", "chicago"]
                for city in cities:
                    if city in content:
                        search_criteria.append(city)
        
        # Build summary
        summary_parts = []
        if preferences:
            summary_parts.append(f"User preferences: {', '.join(set(preferences))}")
        if search_criteria:
            summary_parts.append(f"Destinations discussed: {', '.join(set(search_criteria))}")
        if not summary_parts:
            summary_parts.append("User has been searching for flights and discussing travel options")
        
        return ". ".join(summary_parts) + "."

class FlightChatbotContext:
    """Manages conversation context and flight search capabilities"""
    
    def __init__(self):
        self.system_prompt = """You are a helpful flight booking assistant. 

When users ask about flights, I will provide you with relevant flight data. 
Your job is to present this information in a friendly, helpful way and help users understand their options.

If users ask about anything other than flights, politely redirect them to flight-related topics.

Always be conversational and helpful!"""

async def check_rag_service_connection():
    """Check if RAG service is accessible"""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{RAG_SERVICE_URL}/health")
            if response.status_code == 200:
                print("RAG service connection established")
                return True
            else:
                print(f"RAG service returned status {response.status_code}")
                return False
    except Exception as e:
        print(f"Failed to connect to RAG service: {e}")
        return False


# Remove the old fetch_openai_pricing function as it's now handled by PricingManager

chatbot_context = FlightChatbotContext()
conversation_manager = ConversationManager(max_tokens=15000)

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "llm-service"}

@app.get("/poo")
async def poo():
    return {"status":"i just shit my pants"}

@app.get("/poop")
async def poop():
    return {"status":"i just shit my pants"}


@app.post("/chat", response_model=ChatResponse)
async def chat_with_assistant(request: ChatRequest):
    """Main chat endpoint that handles user queries about flights"""
    try:
        print(f"=== CHAT ENDPOINT START ===")
        print(f"Request: {request.model_dump()}")
        print(f"=== CHAT ENDPOINT START ===")
        conversation_id = request.conversation_id or "default"
        user_message = request.message
        used_flight_search = False
        
        # Add user message to conversation history
        conversation_manager.add_message(conversation_id, "user", user_message)
        
        # Advanced intent detection
        print(f"=== INTENT DETECTION DEBUG ===")
        print(f"User message: {user_message}")
        
        intent_result = await detector.detect_intent(user_message)
        
        if intent_result is None:
            print("ERROR: Intent detector returned None!")
            # Create a fallback result
            intent_result = IntentDetectionResult(
                intent_type=FlightIntentType.CHAT,
                confidence=0.0,
                search_parameters=SearchParameters(),
                original_query=user_message,
                reasoning="Fallback due to None result"
            )
        
        # Normalize intent to plain string to avoid any enum issues
        intent_str = getattr(intent_result.intent_type, "value", str(intent_result.intent_type)).lower()
        
        print(f"Detected intent: {intent_str}")
        print(f"Confidence: {intent_result.confidence}")
        print(f"Parameters: {intent_result.search_parameters}")
        print(f"Reasoning: {intent_result.reasoning}")
        print("=== END INTENT DEBUG ===")
        
        # Determine if we need flight search based on intent type
        if intent_str in ["general_query", "filter_query"] and intent_result.confidence > 0.7:
            # Use RAG service to search for flights
            try:
                # Call the RAG service directly via HTTP
                print(f"=== RAG SERVICE CALL DEBUG ===")
                print(f"Calling flight search with query: {user_message}")
                print(f"Intent type: {intent_str}")
                print(f"Search parameters: {intent_result.search_parameters}")
                print(f"RAG Service URL: {RAG_SERVICE_URL}")
                
                # Pass numerical filters if this is a filter query
                numerical_filters = None
                if intent_str == "filter_query" and intent_result.search_parameters:
                    numerical_filters = intent_result.search_parameters.numerical_filters
                
                flight_results = await call_flight_search_service(user_message, numerical_filters)
                print(f"RAG Service returned: {flight_results}")
                print(f"=== END RAG SERVICE CALL DEBUG ===")
                used_flight_search = True
                
                # Generate response using OpenAI with flight data and conversation context
                messages = await conversation_manager.get_context_messages(conversation_id, chatbot_context.system_prompt)
                
                # Enhance the last user message with flight search results
                enhanced_query = f"""User query: {user_message}

Flight search results:
{flight_results}

Based on the flight search results above, provide a helpful response to the user's query.
Present the flight options clearly and help them understand their choices."""
                
                # Replace the last user message with enhanced version
                if messages and messages[-1]["role"] == "user":
                    messages[-1]["content"] = enhanced_query
                
                response = openai_client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=messages,
                    max_tokens=500
                )
                assistant_response = response.choices[0].message.content
                
            except Exception as e:
                print(f"Flight search error: {e}")
                # Fallback to general response
                assistant_response = "I'm having trouble accessing flight data right now. Please try again in a moment."
        
        else:
            # Handle non-flight queries with conversation context
            messages = await conversation_manager.get_context_messages(conversation_id, chatbot_context.system_prompt)
            
            print(f"=== LLM DEBUG: Calling OpenAI ===")
            print(f"Model: gpt-5-nano")
            print(f"Messages: {messages}")
            
            response = openai_client.chat.completions.create(
                model="gpt-4o-mini",  # Using a known working model
                messages=messages,
                max_tokens=500  # Back to standard parameter
            )
            
            print(f"OpenAI Response: {response}")
            print(f"Choices: {response.choices}")
            print(f"Message content: {response.choices[0].message.content}")
            print(f"Finish reason: {response.choices[0].finish_reason}")
            print("=== END LLM DEBUG ===")
            
            assistant_response = response.choices[0].message.content
        
        # Add assistant response to conversation history
        conversation_manager.add_message(conversation_id, "assistant", assistant_response)
        
        return ChatResponse(
            response=assistant_response,
            conversation_id=conversation_id,
            used_flight_search=used_flight_search,
            detected_intent=intent_str,
            intent_confidence=intent_result.confidence,
            search_parameters=intent_result.search_parameters.model_dump() if intent_result.search_parameters else None
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing chat: {str(e)}")

async def call_flight_search_service(query: str, numerical_filters=None) -> str:
    """Call the RAG service to search for flights"""
    try:
        print(f"RAG Service Call: Making request to {RAG_SERVICE_URL}/search")
        async with httpx.AsyncClient(timeout=15.0) as client:
            # Prepare search payload with optional numerical filters
            search_payload = {"query": query, "max_results": 5}
            if numerical_filters:
                search_payload["numerical_filters"] = numerical_filters.model_dump() if hasattr(numerical_filters, 'model_dump') else numerical_filters
            
            print(f"RAG Service Call: Payload: {search_payload}")
            
            # Call RAG service search endpoint
            response = await client.post(
                f"{RAG_SERVICE_URL}/search",
                json=search_payload
            )
            print(f"RAG Service Call: HTTP Status {response.status_code}")
            response.raise_for_status()
            search_data = response.json()
            print(f"RAG Service Call: Response data: {search_data}")
            
            # Format the results for the LLM
            flights = search_data.get("flights", [])
            if not flights:
                return "No flights found for your search criteria."
            
            result_text = f"Found {len(flights)} flights matching '{query}':\n\n"
            for i, flight in enumerate(flights, 1):
                result_text += f"{i}. Flight {flight['flight_number']} ({flight['airline']})\n"
                result_text += f"   Route: {flight['departure_city']} → {flight['arrival_city']}\n"
                result_text += f"   Departure: {flight['date']} at {flight['departure_time']}\n"
                result_text += f"   Arrival: {flight['date']} at {flight['arrival_time']}\n"
                result_text += f"   Price: ${flight['price']}\n"
                result_text += f"   Aircraft: {flight['aircraft_type']}\n"
                result_text += f"   Available seats: {flight['available_seats']}\n\n"
            
            return result_text
            
    except Exception as e:
        print(f"RAG service call error: {e}")
        return f"Error searching flights: {str(e)}"

@app.get("/rag-service/status")
async def check_rag_service():
    """Check if RAG service is accessible"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{RAG_SERVICE_URL}/health")
            response.raise_for_status()
            return {"rag_service_status": "connected", "details": response.json()}
    except Exception as e:
        return {"rag_service_status": "disconnected", "error": str(e)}

@app.on_event("startup")
async def startup_event():
    """Check RAG service connection when FastAPI starts"""
    print("Starting LLM service...")
    await check_rag_service_connection()
    print("LLM service started successfully")

if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info",
        reload=False,
        workers=1,  # Single worker for MCP client
        access_log=False
    )