"""
Event Schema and Validation for Bucket Chat Protocol

This module defines the core event structure and validation logic
according to the Bucket Chat Protocol specification.
"""

from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, validator
import uuid
import json


class Event(BaseModel):
    """
    Core event structure for Bucket Chat Protocol
    
    All events in the protocol follow this schema, with different
    content based on the event type.
    """
    
    event_id: str = Field(..., description="Unique event identifier")
    room_id: str = Field(..., description="Room identifier")
    timestamp_ms: int = Field(..., description="Unix timestamp in milliseconds")
    sender_id: str = Field(..., description="Sender identifier")
    type: str = Field(..., description="Event type")
    parent_event_id: Optional[str] = Field(None, description="Parent event for threading")
    prev_event_hash: Optional[str] = Field(None, description="Hash of previous event by sender")
    signature: str = Field(..., description="Ed25519 signature")
    content: Dict[str, Any] = Field(..., description="Event content")
    
    @validator('timestamp_ms')
    def validate_timestamp(cls, v):
        """Ensure timestamp is reasonable"""
        if v <= 0:
            raise ValueError("Timestamp must be positive")
        # Check if timestamp is not too far in the future (1 hour)
        now_ms = int(datetime.now().timestamp() * 1000)
        if v > now_ms + 3600000:  # 1 hour in milliseconds
            raise ValueError("Timestamp cannot be more than 1 hour in the future")
        return v
    
    @validator('event_id')
    def validate_event_id(cls, v, values):
        """Validate event ID format"""
        if '::' not in v:
            raise ValueError("Event ID must contain '::' separators")
        parts = v.split('::')
        if len(parts) != 3:
            raise ValueError("Event ID must have exactly 3 parts separated by '::'")
        
        # Check if room_id matches (if available)
        if 'room_id' in values and parts[0] != values['room_id']:
            raise ValueError("Event ID room_id must match event room_id")
        
        return v
    
    @validator('type')
    def validate_event_type(cls, v):
        """Validate event type"""
        valid_types = [
            EventTypes.MESSAGE,
            EventTypes.MEMBER,
            EventTypes.REDACTION,
            EventTypes.EDIT,
            EventTypes.REACTION,
            EventTypes.TYPING
        ]
        if v not in valid_types:
            raise ValueError(f"Invalid event type: {v}")
        return v
    
    @classmethod
    def generate_event_id(cls, room_id: str, timestamp_ms: int) -> str:
        """Generate a unique event ID following the protocol format"""
        timestamp_iso = datetime.fromtimestamp(timestamp_ms / 1000).isoformat() + 'Z'
        unique_id = str(uuid.uuid4())
        return f"{room_id}::{timestamp_iso}::{unique_id}"
    
    def to_jsonl_line(self) -> str:
        """Convert event to JSONL line (JSON + newline)"""
        return self.model_dump_json() + "\n"
    
    @classmethod
    def from_jsonl_line(cls, line: str) -> 'Event':
        """Create event from JSONL line"""
        return cls.model_validate_json(line.strip())
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert event to dictionary"""
        return self.model_dump()
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Event':
        """Create event from dictionary"""
        return cls.model_validate(data)
    
    def is_message(self) -> bool:
        """Check if this is a message event"""
        return self.type == EventTypes.MESSAGE
    
    def is_member_event(self) -> bool:
        """Check if this is a membership event"""
        return self.type == EventTypes.MEMBER
    
    def get_message_body(self) -> Optional[str]:
        """Get message body if this is a message event"""
        if self.is_message():
            return self.content.get('body')
        return None
    
    def get_membership_action(self) -> Optional[str]:
        """Get membership action if this is a member event"""
        if self.is_member_event():
            return self.content.get('membership')
        return None


class EventTypes:
    """Constants for event types as defined in the protocol"""
    
    MESSAGE = "m.room.message"
    MEMBER = "m.room.member"
    REDACTION = "m.room.redaction"
    EDIT = "m.room.edit"
    REACTION = "m.room.reaction"
    TYPING = "m.room.typing"


class MessageContent(BaseModel):
    """Content schema for m.room.message events"""
    
    body: str = Field(..., description="Message text")
    msgtype: str = Field(default="m.text", description="Message type")
    format: Optional[str] = Field(None, description="Message format (e.g., org.matrix.custom.html)")
    formatted_body: Optional[str] = Field(None, description="Formatted message body")
    
    @validator('body')
    def validate_body(cls, v):
        """Ensure message body is not empty"""
        if not v or not v.strip():
            raise ValueError("Message body cannot be empty")
        return v.strip()


class MemberContent(BaseModel):
    """Content schema for m.room.member events"""
    
    membership: str = Field(..., description="Membership action")
    displayname: Optional[str] = Field(None, description="Display name")
    avatar_url: Optional[str] = Field(None, description="Avatar URL")
    reason: Optional[str] = Field(None, description="Reason for membership change")
    
    @validator('membership')
    def validate_membership(cls, v):
        """Validate membership action"""
        valid_actions = ["join", "leave", "invite", "ban", "kick"]
        if v not in valid_actions:
            raise ValueError(f"Invalid membership action: {v}")
        return v


class RedactionContent(BaseModel):
    """Content schema for m.room.redaction events"""
    
    redacts: str = Field(..., description="Event ID being redacted")
    reason: Optional[str] = Field(None, description="Reason for redaction")


class EditContent(BaseModel):
    """Content schema for m.room.edit events"""
    
    replaces: str = Field(..., description="Event ID being edited")
    new_content: MessageContent = Field(..., description="New message content")


class ReactionContent(BaseModel):
    """Content schema for m.room.reaction events"""
    
    relates_to: str = Field(..., description="Event ID being reacted to")
    reaction: str = Field(..., description="Reaction emoji or text")
    
    @validator('reaction')
    def validate_reaction(cls, v):
        """Ensure reaction is not empty"""
        if not v or not v.strip():
            raise ValueError("Reaction cannot be empty")
        return v.strip()


# Event factory functions
def create_message_event(
    room_id: str,
    sender_id: str,
    message: str,
    timestamp_ms: Optional[int] = None,
    parent_event_id: Optional[str] = None,
    prev_event_hash: Optional[str] = None
) -> Dict[str, Any]:
    """Create a message event (unsigned)"""
    if timestamp_ms is None:
        timestamp_ms = int(datetime.now().timestamp() * 1000)
    
    return {
        "event_id": Event.generate_event_id(room_id, timestamp_ms),
        "room_id": room_id,
        "timestamp_ms": timestamp_ms,
        "sender_id": sender_id,
        "type": EventTypes.MESSAGE,
        "parent_event_id": parent_event_id,
        "prev_event_hash": prev_event_hash,
        "signature": "",  # To be filled by signing function
        "content": {
            "body": message.strip(),
            "msgtype": "m.text"
        }
    }


def create_member_event(
    room_id: str,
    sender_id: str,
    membership: str,
    displayname: Optional[str] = None,
    timestamp_ms: Optional[int] = None,
    prev_event_hash: Optional[str] = None
) -> Dict[str, Any]:
    """Create a membership event (unsigned)"""
    if timestamp_ms is None:
        timestamp_ms = int(datetime.now().timestamp() * 1000)
    
    content = {"membership": membership}
    if displayname:
        content["displayname"] = displayname
    
    return {
        "event_id": Event.generate_event_id(room_id, timestamp_ms),
        "room_id": room_id,
        "timestamp_ms": timestamp_ms,
        "sender_id": sender_id,
        "type": EventTypes.MEMBER,
        "parent_event_id": None,
        "prev_event_hash": prev_event_hash,
        "signature": "",  # To be filled by signing function
        "content": content
    }


def create_reaction_event(
    room_id: str,
    sender_id: str,
    target_event_id: str,
    reaction: str,
    timestamp_ms: Optional[int] = None,
    prev_event_hash: Optional[str] = None
) -> Dict[str, Any]:
    """Create a reaction event (unsigned)"""
    if timestamp_ms is None:
        timestamp_ms = int(datetime.now().timestamp() * 1000)
    
    return {
        "event_id": Event.generate_event_id(room_id, timestamp_ms),
        "room_id": room_id,
        "timestamp_ms": timestamp_ms,
        "sender_id": sender_id,
        "type": EventTypes.REACTION,
        "parent_event_id": None,
        "prev_event_hash": prev_event_hash,
        "signature": "",  # To be filled by signing function
        "content": {
            "relates_to": target_event_id,
            "reaction": reaction.strip()
        }
    }


# Utility functions
def validate_event_dict(event_dict: Dict[str, Any]) -> bool:
    """Validate an event dictionary against the schema"""
    try:
        Event.model_validate(event_dict)
        return True
    except Exception:
        return False


def parse_events_from_jsonl(jsonl_content: str) -> List[Event]:
    """Parse events from JSONL content"""
    events = []
    for line in jsonl_content.strip().split('\n'):
        if line.strip():
            try:
                event = Event.from_jsonl_line(line)
                events.append(event)
            except Exception as e:
                # Log error but continue parsing
                print(f"Warning: Failed to parse event line: {e}")
    return events


def events_to_jsonl(events: List[Event]) -> str:
    """Convert list of events to JSONL format"""
    return ''.join(event.to_jsonl_line() for event in events)


if __name__ == "__main__":
    # Simple test
    print("Testing Bucket Chat event system...")
    
    # Create test message event
    event_dict = create_message_event(
        "test_room",
        "alice@example.com", 
        "Hello, World!"
    )
    
    # Validate event
    try:
        event = Event.model_validate(event_dict)
        print(f"✅ Created valid event: {event.event_id}")
        print(f"   Message: {event.get_message_body()}")
        
        # Test JSONL conversion
        jsonl_line = event.to_jsonl_line()
        parsed_event = Event.from_jsonl_line(jsonl_line)
        
        if parsed_event.event_id == event.event_id:
            print("✅ JSONL serialization works correctly")
        else:
            print("❌ JSONL serialization failed")
            
    except Exception as e:
        print(f"❌ Event validation failed: {e}")
    
    print("✅ Event system test completed!")