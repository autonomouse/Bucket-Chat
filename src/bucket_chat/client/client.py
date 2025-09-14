"""
Simple Bucket Chat Client Implementation

This is a simplified version of the client that works with basic authentication
and demonstrates the core protocol functionality.
"""

from typing import Optional, List, Dict, Any
import asyncio
from datetime import datetime, date

from ..core.events import Event, EventTypes, create_message_event, create_member_event
from ..core.storage import UnifiedStorage, generate_client_id, get_date_string
from ..core.crypto import KeyManager, sign_event
from ..auth import SimpleAuth


class BucketChatClient:
    """Simple Bucket Chat client implementation"""
    
    def __init__(self, storage_path: str, user_id: str):
        self.storage = UnifiedStorage(storage_path)
        self.auth = SimpleAuth(user_id)
        self.user_id = user_id
        self.key_manager = KeyManager(user_id)
        self.keypair = None
        self.current_room: Optional[str] = None
        
    async def initialize(self) -> bool:
        """Initialize the client"""
        try:
            # Authenticate
            if not await self.auth.authenticate():
                return False
            
            # Load or create keypair
            self.keypair = self.key_manager.get_or_create_keypair()
            
            return True
        except Exception as e:
            print(f"Failed to initialize client: {e}")
            return False
    
    async def join_room(self, room_id: str) -> bool:
        """Join a chat room"""
        if not self.keypair:
            raise Exception("Client not initialized")
        
        try:
            # Ensure room structure exists
            await self.storage.ensure_room_structure(room_id)
            
            # Send join event
            await self._send_member_event(room_id, "join")
            
            self.current_room = room_id
            return True
        except Exception as e:
            print(f"Failed to join room: {e}")
            return False
    
    async def send_message(self, message: str, room_id: str = None) -> bool:
        """Send a message to a room"""
        room_id = room_id or self.current_room
        if not room_id:
            raise Exception("No room specified")
        
        if not self.keypair:
            raise Exception("Client not initialized")
        
        try:
            # Create message event
            now_ms = int(datetime.now().timestamp() * 1000)
            event_data = create_message_event(
                room_id=room_id,
                sender_id=self.user_id,
                message=message,
                timestamp_ms=now_ms
            )
            
            # Sign event
            signed_event = sign_event(event_data, self.keypair)
            event = Event(**signed_event)
            
            # Write to storage
            await self._write_event_to_storage(event)
            
            return True
        except Exception as e:
            print(f"Failed to send message: {e}")
            return False
    
    async def get_messages(self, room_id: str, limit: int = 50) -> List[Event]:
        """Get recent messages from a room"""
        try:
            # Get recent log files
            log_files = await self.storage.list_log_files(room_id)
            
            events = []
            # Read from the most recent files first
            for file_path in reversed(log_files[-10:]):  # Last 10 files
                lines = await self.storage.read_jsonl_file(file_path)
                for line in lines:
                    try:
                        event = Event.from_jsonl_line(line)
                        if event.type == EventTypes.MESSAGE:
                            events.append(event)
                    except Exception as e:
                        print(f"Warning: Failed to parse event: {e}")
            
            # Sort by timestamp and return recent messages
            events.sort(key=lambda e: e.timestamp_ms)
            return events[-limit:]
        except Exception as e:
            print(f"Failed to get messages: {e}")
            return []
    
    async def leave_room(self, room_id: str = None) -> bool:
        """Leave a chat room"""
        room_id = room_id or self.current_room
        if not room_id:
            return True
        
        try:
            # Send leave event
            await self._send_member_event(room_id, "leave")
            
            if room_id == self.current_room:
                self.current_room = None
            
            return True
        except Exception as e:
            print(f"Failed to leave room: {e}")
            return False
    
    async def _send_member_event(self, room_id: str, membership: str):
        """Send a membership event"""
        now_ms = int(datetime.now().timestamp() * 1000)
        event_data = create_member_event(
            room_id=room_id,
            sender_id=self.user_id,
            membership=membership,
            displayname=self.user_id,
            timestamp_ms=now_ms
        )
        
        # Sign event
        signed_event = sign_event(event_data, self.keypair)
        event = Event(**signed_event)
        
        # Write to storage
        await self._write_event_to_storage(event)
    
    async def _write_event_to_storage(self, event: Event):
        """Write an event to storage"""
        # Get date for file organization
        event_date = get_date_string(event.timestamp_ms)
        client_id = generate_client_id(self.user_id)
        
        # Create file path
        file_path = self.storage.get_daily_log_path(
            event.room_id,
            event_date,
            event.timestamp_ms,
            event.timestamp_ms,
            client_id
        )
        
        # Write event to file
        success = await self.storage.write_jsonl_file(file_path, [event.to_jsonl_line()])
        if not success:
            raise Exception("Failed to write event to storage")
    
    def get_user_info(self) -> Dict[str, Any]:
        """Get current user information"""
        return {
            'user_id': self.user_id,
            'current_room': self.current_room,
            'public_key': self.keypair.public_key_base64() if self.keypair else None,
            'authenticated': self.auth.is_authenticated
        }
    
    async def get_room_info(self, room_id: str) -> Optional[Dict[str, Any]]:
        """Get room information"""
        try:
            metadata = await self.storage.get_room_metadata(room_id)
            if metadata:
                # Add some computed info
                log_files = await self.storage.list_log_files(room_id)
                metadata['log_files_count'] = len(log_files)
                
                # Get message count (approximate)
                message_count = 0
                for file_path in log_files[-5:]:  # Check last 5 files
                    lines = await self.storage.read_jsonl_file(file_path)
                    message_count += len([l for l in lines if '"type":"m.room.message"' in l])
                
                metadata['recent_message_count'] = message_count
            
            return metadata
        except Exception as e:
            print(f"Failed to get room info: {e}")
            return None


if __name__ == "__main__":
    # Simple test
    async def test_client():
        print("Testing Bucket Chat client...")
        
        # Create client
        client = BucketChatClient("./test-client-storage", "alice@example.com")
        
        # Initialize
        if not await client.initialize():
            print("❌ Failed to initialize client")
            return
        
        print("✅ Client initialized")
        print(f"User info: {client.get_user_info()}")
        
        # Join room
        if not await client.join_room("test_room"):
            print("❌ Failed to join room")
            return
        
        print("✅ Joined room")
        
        # Send messages
        messages = ["Hello, World!", "This is a test message", "Bucket Chat is working!"]
        for msg in messages:
            if not await client.send_message(msg):
                print(f"❌ Failed to send message: {msg}")
                return
            print(f"✅ Sent: {msg}")
        
        # Get messages
        received_messages = await client.get_messages("test_room")
        print(f"✅ Retrieved {len(received_messages)} messages")
        
        for event in received_messages:
            print(f"  {event.sender_id}: {event.get_message_body()}")
        
        # Get room info
        room_info = await client.get_room_info("test_room")
        print(f"✅ Room info: {room_info}")
        
        print("✅ Client test completed!")
    
    asyncio.run(test_client())