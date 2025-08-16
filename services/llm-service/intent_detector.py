"""
Advanced Intent Detection System for Flight Search
Uses LangChain and structured prompting for accurate intent classification
"""

from enum import Enum
from typing import Dict, Any, Optional
from pydantic import BaseModel
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
import os

class FlightIntentType(str, Enum):
    """Three-category intent classification for enhanced filtering"""
    
    GENERAL_QUERY = "general_query"  # Basic flight search without specific numerical criteria
    FILTER_QUERY = "filter_query"    # Flight search with specific numerical filters (price, time, seats, etc.)
    CHAT = "chat"                    # General conversation, greetings, non-flight topics

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

class SearchParameters(BaseModel):
    """Enhanced search parameters with numerical filtering"""
    origin: Optional[str] = None
    destination: Optional[str] = None
    airline: Optional[str] = None
    date: Optional[str] = None
    price_preference: Optional[str] = None  # "cheap", "premium", "any"
    class_preference: Optional[str] = None  # "economy", "business", "first"
    time_preference: Optional[str] = None  # "morning", "afternoon", "evening"
    flexibility: Optional[str] = None  # "exact", "flexible", "very_flexible"
    numerical_filters: Optional[NumericalFilters] = None

class IntentDetectionResult(BaseModel):
    """Structured result of intent detection"""
    intent_type: FlightIntentType
    confidence: float  # 0.0 to 1.0
    search_parameters: SearchParameters
    original_query: str
    reasoning: str  # Why this intent was chosen

class FlightIntentDetector:
    """Advanced intent detector using LangChain and structured prompting"""
    
    def __init__(self, api_key: str, model_name: str = "gpt-4o-mini"):
        self.llm = ChatOpenAI(
            api_key=api_key,
            model=model_name,
            temperature=0.1  # Low temperature for consistent classification
        )
        self.parser = PydanticOutputParser(pydantic_object=IntentDetectionResult)
        self.prompt = self._create_intent_prompt()
    
    def _create_intent_prompt(self) -> ChatPromptTemplate:
        """Create the one-shot intent classification prompt"""
        
        # Simple 3 examples - one for each intent type
        examples = """
Examples:

User: "Find flights from New York to Los Angeles"
Intent: general_query
Reason: Basic flight search without specific numbers

User: "Show me flights under $500 to Miami"  
Intent: filter_query
Reason: Flight search with specific price number ($500)

User: "Hello, how are you today?"
Intent: chat
Reason: General conversation, not about flights
"""

        prompt_template = """You are an intent classifier. Classify user queries into exactly one category:

- **general_query**: Flight searches without specific numbers  
- **filter_query**: Flight searches WITH specific numbers (prices, times, seat counts)
- **chat**: Not about flights

{examples}

RULES:
- If query mentions flights + specific numbers/prices → filter_query
- If query mentions flights without specific numbers → general_query  
- If not about flights → chat

User Query: "{{user_query}}"

Respond with valid JSON only:
{{
  "intent_type": "general_query" or "filter_query" or "chat", 
  "confidence": 0.9,
  "search_parameters": {{"origin": null, "destination": null, "numerical_filters": null}},
  "original_query": "{{user_query}}",
  "reasoning": "Brief explanation"
}}"""

        return ChatPromptTemplate.from_template(prompt_template)
    
    async def detect_intent(self, user_query: str) -> IntentDetectionResult:
        """Detect intent from user query using LLM classification"""
        print(f"=== INTENT DETECTOR START ===")
        print(f"Input query: {user_query}")
        try:
            # Create simple prompt manually to avoid LangChain complexity
            simple_prompt = """You are an intent classifier. Classify user queries into exactly one category:

- **general_query**: Flight searches without specific numbers  
- **filter_query**: Flight searches WITH specific numbers (prices, times, seat counts)
- **chat**: Not about flights

Examples:

User: "Find flights from New York to Los Angeles"
Intent: general_query
Reason: Basic flight search without specific numbers

User: "Show me flights under $500 to Miami"  
Intent: filter_query
Reason: Flight search with specific price number ($500)

User: "Hello, how are you today?"
Intent: chat
Reason: General conversation, not about flights

RULES:
- If query mentions flights + specific numbers/prices → filter_query
- If query mentions flights without specific numbers → general_query  
- If not about flights → chat

User Query: "{}"

Respond with valid JSON only:
{{
  "intent_type": "filter_query",
  "confidence": 0.9,
  "search_parameters": {{"origin": null, "destination": "Miami", "numerical_filters": {{"max_price": 500}}}},
  "original_query": "{}",
  "reasoning": "Flight search with price filter"
}}""".format(user_query, user_query)
            
            # Use LLM directly without LangChain prompt formatting
            from langchain_core.messages import HumanMessage
            messages = [HumanMessage(content=simple_prompt)]
            
            # Get LLM response
            print(f"=== CALLING LLM ===")
            print(f"Messages: {messages}")
            response = await self.llm.ainvoke(messages)
            print(f"=== LLM RESPONSE RECEIVED ===")
            print(f"Response type: {type(response)}")
            print(f"Response: {response}")
            
            # Debug: Print raw LLM response
            print(f"=== RAW LLM RESPONSE ===")
            print(f"Content: {response.content}")
            print(f"=== END RAW RESPONSE ===")
            
            # Manual JSON parsing instead of PydanticOutputParser
            try:
                import json
                
                # Strip markdown code blocks if present
                content = response.content.strip()
                print(f"=== CONTENT BEFORE STRIPPING ===")
                print(f"Content: {repr(content)}")
                
                # Remove leading markdown
                if content.startswith("```json"):
                    content = content[7:]  # Remove ```json
                elif content.startswith("```"):
                    content = content[3:]   # Remove ```
                content = content.strip()  # Remove any leading/trailing whitespace
                
                # Remove trailing markdown
                if content.endswith("```"):
                    content = content[:-3]  # Remove trailing ```
                content = content.strip()  # Remove any remaining whitespace
                
                print(f"=== CONTENT AFTER STRIPPING ===")
                print(f"Content: {repr(content)}")
                
                response_json = json.loads(content)
                
                # Extract numerical filters if present
                numerical_filters = None
                if "numerical_filters" in response_json.get("search_parameters", {}):
                    filters_data = response_json["search_parameters"]["numerical_filters"]
                    if filters_data:
                        numerical_filters = NumericalFilters(**filters_data)
                
                # Create search parameters
                search_params_data = response_json.get("search_parameters", {})
                search_params = SearchParameters(
                    origin=search_params_data.get("origin"),
                    destination=search_params_data.get("destination"),
                    airline=search_params_data.get("airline"),
                    numerical_filters=numerical_filters
                )
                
                # Create intent result
                intent_result = IntentDetectionResult(
                    intent_type=FlightIntentType(response_json["intent_type"]),
                    confidence=response_json.get("confidence", 0.8),
                    search_parameters=search_params,
                    original_query=user_query,
                    reasoning=response_json.get("reasoning", "Manual parsing")
                )
                
                print(f"=== INTENT DETECTOR SUCCESS ===")
                return intent_result
                
            except Exception as parse_error:
                print(f"=== MANUAL PARSE ERROR ===")
                print(f"Parse error: {str(parse_error)}")
                print(f"Raw response: {response.content}")
                print(f"=== END MANUAL PARSE ERROR ===")
                # Let it fall through to the except block
            
        except Exception as e:
            print(f"=== INTENT DETECTOR EXCEPTION ===")
            print(f"Exception: {str(e)}")
            print(f"Exception type: {type(e)}")
            import traceback
            print(f"Traceback: {traceback.format_exc()}")
            print(f"=== END INTENT DETECTOR EXCEPTION ===")
            # Fallback to chat intent with basic parameter extraction
            return IntentDetectionResult(
                intent_type=FlightIntentType.CHAT,
                confidence=0.0,
                search_parameters=self._extract_basic_parameters(user_query),
                original_query=user_query,
                reasoning=f"Error in classification: {str(e)}"
            )
        
        # This should never be reached
        print(f"=== ERROR: REACHED END OF METHOD WITHOUT RETURN ===")
        return None
    
    def _extract_basic_parameters(self, query: str) -> SearchParameters:
        """Basic parameter extraction as fallback"""
        query_lower = query.lower()
        
        # Simple keyword-based extraction for fallback
        origin = None
        destination = None
        airline = None
        
        # Look for common patterns
        if " from " in query_lower and " to " in query_lower:
            parts = query_lower.split(" from ")[1].split(" to ")
            if len(parts) >= 2:
                origin = parts[0].strip()
                destination = parts[1].split()[0].strip()
        
        # Look for price preferences
        price_pref = None
        if any(word in query_lower for word in ["cheap", "budget", "affordable"]):
            price_pref = "cheap"
        elif any(word in query_lower for word in ["premium", "business", "first"]):
            price_pref = "premium"
        
        return SearchParameters(
            origin=origin,
            destination=destination,
            airline=airline,
            price_preference=price_pref
        )

# Factory function for easy integration
def create_intent_detector(api_key: str) -> FlightIntentDetector:
    """Create and return a configured intent detector"""
    return FlightIntentDetector(api_key)

# Example usage and testing
async def test_intent_detection():
    """Test the intent detector with various queries"""
    
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("OPENAI_API_KEY not found")
        return
    
    detector = create_intent_detector(api_key)
    
    test_queries = [
        "Find flights from New York to Los Angeles",
        "Show me cheap flights to Europe", 
        "What American Airlines flights are available?",
        "I need a business class flight tomorrow",
        "Compare prices for flights to Miami",
        "What's the status of flight AA123?",
        "Book me a flight",
        "Hello, how are you?",
        "What's the weather like?",
        "Tell me a joke",
        "How are you doing today?",
        "Can you help me find flights under $300?",
    ]
    
    print("Testing Intent Detection System")
    print("=" * 50)
    
    for query in test_queries:
        result = await detector.detect_intent(query)
        print(f"\nQuery: '{query}'")
        print(f"Intent: {result.intent_type}")
        print(f"Confidence: {result.confidence:.2f}")
        print(f"Parameters: {result.search_parameters}")
        print(f"Reasoning: {result.reasoning}")

if __name__ == "__main__":
    import asyncio
    from dotenv import load_dotenv
    
    load_dotenv()
    asyncio.run(test_intent_detection())