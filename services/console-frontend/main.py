import httpx
import asyncio
import os
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.prompt import Prompt
from rich.table import Table
from rich.live import Live
from rich.spinner import Spinner
import json
from typing import Optional
import uuid
import time
from dotenv import load_dotenv

# Rich console for beautiful output
console = Console()

# LLM Service connection
LLM_SERVICE_URL = os.getenv("LLM_SERVICE_URL", "http://localhost:8080")

class FlightChatInterface:
    """Interactive console interface for the flight chatbot"""
    
    def __init__(self):
        self.conversation_id = str(uuid.uuid4())
        self.session_active = True
        
    def display_welcome(self):
        """Display welcome message and instructions"""
        welcome_text = Text()
        welcome_text.append("🛫 ", style="cyan")
        welcome_text.append("Flight Booking Assistant", style="bold cyan")
        welcome_text.append(" 🛬", style="cyan")
        
        welcome_panel = Panel(
            welcome_text,
            title="Welcome",
            border_style="cyan",
            padding=(1, 2)
        )
        console.print(welcome_panel)
        
        instructions = """
        I can help you search for flights! Try asking me things like:
        
        • "Find flights from NYC to LAX tomorrow"
        • "Show me flights to Paris next week"
        • "I need a flight from Chicago to Miami"
        • "What flights are available from Boston to Seattle?"
        
        Type 'quit' or 'exit' to end the conversation.
        Type 'help' for more information.
        """
        
        console.print(Panel(instructions, title="How to Use", border_style="green"))
        console.print()

    def display_help(self):
        """Display help information"""
        help_table = Table(title="Available Commands", border_style="blue")
        help_table.add_column("Command", style="cyan", no_wrap=True)
        help_table.add_column("Description", style="white")
        
        help_table.add_row("help", "Show this help message")
        help_table.add_row("quit / exit", "End the conversation")
        help_table.add_row("status", "Check service health")
        help_table.add_row("clear", "Clear the screen")
        
        console.print(help_table)
        console.print()

    async def check_service_health(self):
        """Check if all services are running and display status"""
        with console.status("[bold green]Checking services...", spinner="dots"):
            services_ok = await self.validate_services()
            
        console.print()
        return services_ok
    
    async def validate_services(self) -> bool:
        """Validate that services are accessible - returns True if all OK"""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Check LLM service
                llm_response = await client.get(f"{LLM_SERVICE_URL}/health")
                llm_ok = llm_response.status_code == 200
                llm_status = "✅ Online" if llm_ok else "❌ Offline"
                
                # Check RAG service through LLM service
                rag_response = await client.get(f"{LLM_SERVICE_URL}/rag-service/status")
                rag_data = rag_response.json()
                rag_ok = rag_data.get("rag_service_status") == "connected"
                rag_status = "✅ Online" if rag_ok else "❌ Offline"
                
            status_table = Table(title="Service Status", border_style="green")
            status_table.add_column("Service", style="cyan")
            status_table.add_column("Status", style="white")
            
            status_table.add_row("LLM Service", llm_status)
            status_table.add_row("RAG Service", rag_status)
            status_table.add_row("Vector Database", "✅ Online" if rag_ok else "❌ Offline")
            
            console.print(status_table)
            
            return llm_ok and rag_ok
            
        except Exception as e:
            console.print(f"[red]Error checking services: {e}[/red]")
            return False

    async def send_message(self, message: str) -> Optional[str]:
        """Send message to LLM service and get response"""
        try:
            print(f"\n=== DEBUG: Sending message to {LLM_SERVICE_URL}/chat ===")
            print(f"Message: {message}")
            print(f"Conversation ID: {self.conversation_id}")
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                request_data = {
                    "message": message,
                    "conversation_id": self.conversation_id
                }
                print(f"Request data: {request_data}")
                
                response = await client.post(
                    f"{LLM_SERVICE_URL}/chat",
                    json=request_data
                )
                
                print(f"HTTP Status: {response.status_code}")
                response.raise_for_status()
                
                response_data = response.json()
                print(f"Full response: {response_data}")
                print(f"Response text: {response_data.get('response', 'NO RESPONSE FIELD')}")
                print(f"Used flight search: {response_data.get('used_flight_search', 'NO FIELD')}")
                print("=== END DEBUG ===\n")
                
                return response_data
                
        except httpx.TimeoutException:
            console.print("[red]Request timed out. The service might be busy.[/red]")
            return None
        except httpx.RequestError as e:
            console.print(f"[red]Connection error: {e}[/red]")
            return None
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            return None

    def display_response(self, response_data: dict):
        """Display the chatbot response with formatting"""
        print(f"\n=== DEBUG: Displaying response ===")
        print(f"Response data: {response_data}")
        
        if not response_data:
            print("No response data!")
            return
            
        response_text = response_data.get("response", "No response received")
        used_flight_search = response_data.get("used_flight_search", False)
        
        print(f"Response text: '{response_text}'")
        print(f"Used flight search: {used_flight_search}")
        print(f"Response text length: {len(response_text) if response_text else 0}")
        print("=== END DISPLAY DEBUG ===\n")
        
        # Add indicator if flight search was used
        title = "Flight Assistant"
        if used_flight_search:
            title += " 🔍"
            
        response_panel = Panel(
            response_text,
            title=title,
            border_style="blue" if used_flight_search else "yellow",
            padding=(1, 2)
        )
        
        console.print(response_panel)
        console.print()

    async def run_chat_loop(self):
        """Main chat interaction loop"""
        while self.session_active:
            try:
                # Get user input
                user_input = Prompt.ask(
                    "[bold cyan]You[/bold cyan]",
                    default=""
                ).strip()
                
                if not user_input:
                    continue
                    
                # Handle special commands
                if user_input.lower() in ['quit', 'exit']:
                    console.print("[yellow]Thanks for using the Flight Assistant! Safe travels! ✈️[/yellow]")
                    break
                    
                elif user_input.lower() == 'help':
                    self.display_help()
                    continue
                    
                elif user_input.lower() == 'status':
                    await self.check_service_health()
                    continue
                    
                elif user_input.lower() == 'clear':
                    console.clear()
                    self.display_welcome()
                    continue
                
                # Send message to chatbot
                with console.status("[bold green]Thinking...", spinner="dots"):
                    response_data = await self.send_message(user_input)
                
                self.display_response(response_data)
                
            except KeyboardInterrupt:
                console.print("\n[yellow]Goodbye! ✈️[/yellow]")
                break
            except Exception as e:
                console.print(f"[red]Unexpected error: {e}[/red]")

async def main():
    """Main application entry point"""
    # Load environment variables
    load_dotenv()
    
    chat_interface = FlightChatInterface()
    
    # Clear screen and show welcome
    console.clear()
    chat_interface.display_welcome()
    
    # Startup validation with retries
    max_retries = 3
    services_ready = False
    
    for attempt in range(max_retries):
        console.print(f"[cyan]Checking services... (attempt {attempt + 1}/{max_retries})[/cyan]")
        services_ready = await chat_interface.check_service_health()
        
        if services_ready:
            console.print("[green]✅ All services ready! Starting chat...[/green]")
            break
        elif attempt < max_retries - 1:
            console.print("[yellow]⚠️ Services not ready, retrying in 3 seconds...[/yellow]")
            await asyncio.sleep(3)
    
    if not services_ready:
        console.print("[red]❌ Services are not responding[/red]")
        choice = Prompt.ask(
            "What would you like to do?",
            choices=["continue", "quit"],
            default="continue"
        )
        
        if choice == "quit":
            console.print("[yellow]Goodbye! ✈️[/yellow]")
            return
        else:
            console.print("[yellow]⚠️ Running in limited mode - some features may not work[/yellow]")
    
    console.print()
    # Start chat loop
    await chat_interface.run_chat_loop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[yellow]Goodbye! ✈️[/yellow]")
    except Exception as e:
        console.print(f"[red]Fatal error: {e}[/red]")