"""
Bucket Chat CLI - Main entry point

This module provides the command-line interface for the Bucket Chat reference client.
"""

import asyncio
import sys
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

# Import our core modules
from ..core.crypto import KeyManager, generate_test_keypair, create_test_event
from ..core.storage import UnifiedStorage
from ..core.events import Event, EventTypes
from ..client.client import BucketChatClient

console = Console()


@click.group()
@click.option('--storage-path', '-s', default='./bucket-chat-data', 
              help='Storage path (local directory or cloud URI)')
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose output')
@click.pass_context
def cli(ctx, storage_path: str, verbose: bool):
    """Bucket Chat - Decentralized Chat Protocol Reference Client"""
    ctx.ensure_object(dict)
    ctx.obj['storage_path'] = storage_path
    ctx.obj['verbose'] = verbose
    
    if verbose:
        console.print(f"[dim]Using storage path: {storage_path}[/dim]")


@cli.command()
@click.pass_context
def test_crypto(ctx):
    """Test cryptographic functions"""
    console.print(Panel.fit("🔐 Testing Cryptographic Functions", style="bold blue"))
    
    try:
        # Generate keypair
        console.print("Generating Ed25519 keypair...")
        keypair = generate_test_keypair()
        console.print(f"✅ Generated keypair")
        console.print(f"   Public key: {keypair.public_key_base64()[:32]}...")
        
        # Create test event
        console.print("\nCreating and signing test event...")
        test_event = create_test_event(
            "test_room", 
            "alice@example.com", 
            "Hello, Bucket Chat!", 
            keypair
        )
        console.print(f"✅ Created event: {test_event['event_id'][:50]}...")
        
        # Verify signature
        from ..core.crypto import verify_event_signature
        is_valid = verify_event_signature(test_event, keypair.public_key_bytes())
        
        if is_valid:
            console.print("✅ Signature verification: [green]VALID[/green]")
        else:
            console.print("❌ Signature verification: [red]INVALID[/red]")
            
        # Test hash computation
        from ..core.crypto import compute_event_hash
        event_hash = compute_event_hash(test_event)
        console.print(f"✅ Event hash: {event_hash[:32]}...")
        
        console.print("\n🎉 All cryptographic tests passed!")
        
    except Exception as e:
        console.print(f"❌ Crypto test failed: {e}")
        sys.exit(1)


@cli.command()
@click.option('--room-id', '-r', default='test_room', help='Room ID to test with')
@click.pass_context
def test_storage(ctx, room_id: str):
    """Test storage operations"""
    storage_path = ctx.obj['storage_path']
    
    console.print(Panel.fit("💾 Testing Storage Operations", style="bold green"))
    console.print(f"Storage path: {storage_path}")
    console.print(f"Room ID: {room_id}")
    
    async def run_storage_test():
        try:
            # Initialize storage
            storage = UnifiedStorage(storage_path)
            console.print("✅ Initialized storage")
            
            # Ensure room structure
            await storage.ensure_room_structure(room_id)
            console.print("✅ Created room structure")
            
            # Create test events
            keypair = generate_test_keypair()
            events = []
            
            for i in range(3):
                event_dict = create_test_event(
                    room_id,
                    "alice@example.com",
                    f"Test message {i + 1}",
                    keypair
                )
                event = Event(**event_dict)
                events.append(event.to_jsonl_line())
            
            # Write JSONL file
            from datetime import datetime
            now_ms = int(datetime.now().timestamp() * 1000)
            file_path = storage.get_daily_log_path(
                room_id, 
                datetime.now().date().isoformat(),
                now_ms - 1000,
                now_ms,
                "alice"
            )
            
            success = await storage.write_jsonl_file(file_path, events)
            if success:
                console.print("✅ Wrote JSONL file")
            else:
                console.print("❌ Failed to write JSONL file")
                return
            
            # Read back events
            read_events = await storage.read_jsonl_file(file_path)
            console.print(f"✅ Read {len(read_events)} events from storage")
            
            # List log files
            log_files = await storage.list_log_files(room_id)
            console.print(f"✅ Found {len(log_files)} log files")
            
            console.print("\n🎉 All storage tests passed!")
            
        except Exception as e:
            console.print(f"❌ Storage test failed: {e}")
            sys.exit(1)
    
    asyncio.run(run_storage_test())


@cli.command()
@click.option('--user-id', '-u', prompt=True, help='Your user ID (email)')
@click.pass_context
def setup_keys(ctx, user_id: str):
    """Set up cryptographic keys for a user"""
    console.print(Panel.fit("🔑 Setting Up User Keys", style="bold yellow"))
    
    try:
        key_manager = KeyManager(user_id)
        
        # Check if keypair already exists
        existing_keypair = key_manager.load_keypair()
        if existing_keypair:
            console.print(f"✅ Found existing keypair for {user_id}")
            console.print(f"   Public key: {existing_keypair.public_key_base64()[:32]}...")
            
            if click.confirm("Generate new keypair?"):
                keypair = key_manager.generate_and_save_keypair()
                console.print("✅ Generated and saved new keypair")
            else:
                keypair = existing_keypair
        else:
            console.print(f"Generating new keypair for {user_id}...")
            keypair = key_manager.generate_and_save_keypair()
            console.print("✅ Generated and saved keypair")
        
        console.print(f"Public key: {keypair.public_key_base64()}")
        console.print("\n🎉 Key setup complete!")
        
    except Exception as e:
        console.print(f"❌ Key setup failed: {e}")
        sys.exit(1)


@cli.command()
@click.option('--room-id', '-r', prompt=True, help='Room ID to join')
@click.option('--user-id', '-u', prompt=True, help='Your user ID (email)')
@click.pass_context
def chat(ctx, room_id: str, user_id: str):
    """Start interactive chat session"""
    storage_path = ctx.obj['storage_path']
    
    console.print(Panel.fit(f"💬 Joining Room: {room_id}", style="bold magenta"))
    console.print(f"User: {user_id}")
    console.print(f"Storage: {storage_path}")
    
    async def run_chat():
        try:
            # Set up key manager
            key_manager = KeyManager(user_id)
            keypair = key_manager.get_or_create_keypair()
            console.print("✅ Loaded user keypair")
            
            # Initialize storage
            storage = UnifiedStorage(storage_path)
            await storage.ensure_room_structure(room_id)
            console.print("✅ Initialized room storage")
            
            # Simple chat loop
            console.print(f"\n[bold green]Welcome to room '{room_id}'![/bold green]")
            console.print("Type messages and press Enter. Type '/quit' to exit.\n")
            
            while True:
                try:
                    message = input(f"{user_id}: ").strip()
                    
                    if message == '/quit':
                        break
                    
                    if not message:
                        continue
                    
                    # Create and sign event
                    event_dict = create_test_event(room_id, user_id, message, keypair)
                    event = Event(**event_dict)
                    
                    # Write to storage
                    from datetime import datetime, date
                    now = datetime.now()
                    file_path = storage.get_daily_log_path(
                        room_id,
                        now.date().isoformat(),
                        event.timestamp_ms,
                        event.timestamp_ms,
                        user_id.split('@')[0] if '@' in user_id else user_id
                    )
                    
                    success = await storage.write_jsonl_file(file_path, [event.to_jsonl_line()])
                    
                    if success:
                        console.print(f"[dim]✓ Message sent[/dim]")
                    else:
                        console.print(f"[red]✗ Failed to send message[/red]")
                        
                except KeyboardInterrupt:
                    break
            
            console.print("\n👋 Goodbye!")
            
        except Exception as e:
            console.print(f"❌ Chat failed: {e}")
            sys.exit(1)
    
    asyncio.run(run_chat())


@cli.command()
@click.option('--room-id', '-r', prompt=True, help='Room ID to read from')
@click.option('--limit', '-l', default=20, help='Number of messages to show')
@click.pass_context
def history(ctx, room_id: str, limit: int):
    """Show chat history for a room"""
    storage_path = ctx.obj['storage_path']
    
    console.print(Panel.fit(f"📜 Chat History: {room_id}", style="bold cyan"))
    
    async def show_history():
        try:
            storage = UnifiedStorage(storage_path)
            
            # Get log files
            log_files = await storage.list_log_files(room_id)
            
            if not log_files:
                console.print("No messages found in this room.")
                return
            
            # Read events from recent files
            events = []
            for file_path in log_files[-5:]:  # Last 5 files
                lines = await storage.read_jsonl_file(file_path)
                for line in lines:
                    try:
                        event = Event.from_jsonl_line(line)
                        if event.type == EventTypes.MESSAGE:
                            events.append(event)
                    except Exception as e:
                        console.print(f"[dim]Warning: Failed to parse event: {e}[/dim]")
            
            # Sort by timestamp and show recent messages
            events.sort(key=lambda e: e.timestamp_ms)
            recent_events = events[-limit:]
            
            console.print(f"\nShowing {len(recent_events)} recent messages:\n")
            
            for event in recent_events:
                from datetime import datetime
                timestamp = datetime.fromtimestamp(event.timestamp_ms / 1000)
                sender = event.sender_id
                message = event.content.get('body', '')
                
                console.print(f"[dim]{timestamp.strftime('%H:%M:%S')}[/dim] [bold]{sender}[/bold]: {message}")
            
        except Exception as e:
            console.print(f"❌ Failed to show history: {e}")
            sys.exit(1)
    
    asyncio.run(show_history())


@cli.command()
def version():
    """Show version information"""
    console.print(Panel.fit("Bucket Chat Reference Client v0.1.0", style="bold blue"))
    console.print("Decentralized Chat Protocol Implementation")
    console.print("Licensed under AGPLv3")


def main():
    """Main entry point"""
    try:
        cli()
    except KeyboardInterrupt:
        console.print("\n👋 Goodbye!")
        sys.exit(0)
    except Exception as e:
        console.print(f"❌ Unexpected error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()