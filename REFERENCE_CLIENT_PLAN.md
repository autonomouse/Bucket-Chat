# Bucket Chat Reference Terminal Client - Implementation Plan

## Overview

This document outlines the implementation of a terminal-based Python client as the reference implementation for the Bucket Chat Protocol. The client will feature OAuth 2.0 authentication and unified local/cloud storage access using `cloudpathlib`.

## Key Features

- **Terminal-first experience**: Rich, interactive command-line interface
- **OAuth 2.0 authentication**: Support for Google, Microsoft, and generic OAuth providers
- **Unified storage**: Seamless operation on local filesystem and cloud storage (S3, GCS, Azure)
- **Real-time sync**: File system monitoring and optional MQTT/WebSocket sync
- **Secure credential management**: OS keyring integration for token storage
- **Cross-platform**: Works on Windows, macOS, and Linux

## Dependencies

```toml
# Core dependencies
cloudpathlib[all]>=0.16.0         # Unified cloud/local storage interface
cryptography>=41.0.0              # Ed25519 signatures and hashing
pydantic>=2.0.0                   # Data validation and settings
click>=8.1.0                      # Command-line interface
rich>=13.0.0                      # Rich terminal output
textual>=0.40.0                   # Terminal UI framework
httpx>=0.25.0                     # Async HTTP client
python-jose>=3.3.0                # JWT token handling
keyring>=24.0.0                   # Secure credential storage
watchdog>=3.0.0                   # File system monitoring
aiofiles>=23.0.0                  # Async file operations

# OAuth 2.0 authentication
authlib>=1.2.0                    # OAuth 2.0 client library
google-auth>=2.23.0               # Google OAuth
google-auth-oauthlib>=1.1.0       # Google OAuth flow
msal>=1.24.0                      # Microsoft OAuth

# Terminal UI enhancements
prompt-toolkit>=3.0.0             # Advanced terminal input
colorama>=0.4.0                   # Cross-platform colored output
blessed>=1.20.0                   # Terminal capabilities

# Configuration and settings
python-dotenv>=1.0.0              # Environment variable loading
toml>=0.10.0                      # TOML configuration files

# Development and testing
pytest>=7.4.0                     # Testing framework
pytest-asyncio>=0.21.0            # Async testing
pytest-cov>=4.1.0                # Coverage reporting
pytest-mock>=3.11.0               # Mocking utilities
black>=23.0.0                     # Code formatting
mypy>=1.5.0                       # Type checking
flake8>=6.0.0                     # Linting
isort>=5.12.0                     # Import sorting

# Optional: Real-time sync (for advanced features)
asyncio-mqtt>=0.13.0              # MQTT client for real-time sync
websockets>=11.0.0                # WebSocket support

# Optional: Performance monitoring
psutil>=5.9.0                     # System resource monitoring

# Build and packaging
setuptools>=68.0.0
wheel>=0.41.0
build>=0.10.0
```

## Project Structure

```
bucket-chat-client/
├── src/
│   └── bucket_chat/
│       ├── __init__.py
│       ├── core/                      # Core protocol implementation
│       │   ├── __init__.py
│       │   ├── events.py              # Event schema and validation
│       │   ├── crypto.py              # Cryptographic operations
│       │   ├── storage.py             # Unified storage interface
│       │   └── timeline.py            # Timeline reconstruction
│       ├── auth/                      # Authentication module
│       │   ├── __init__.py
│       │   ├── oauth.py               # OAuth 2.0 flows
│       │   ├── providers.py           # OAuth provider configs
│       │   └── credentials.py         # Credential management
│       ├── client/                    # Client implementation
│       │   ├── __init__.py
│       │   ├── room.py                # Room management
│       │   ├── sync.py                # Synchronization logic
│       │   └── buffer.py              # Message buffering
│       ├── ui/                        # Terminal UI components
│       │   ├── __init__.py
│       │   ├── chat.py                # Chat interface
│       │   ├── commands.py            # Command handlers
│       │   └── widgets.py             # Custom UI widgets
│       ├── config/                    # Configuration management
│       │   ├── __init__.py
│       │   ├── settings.py            # Settings schema
│       │   └── profiles.py            # User profiles
│       └── utils/                     # Utility functions
│           ├── __init__.py
│           ├── paths.py               # Path utilities
│           ├── logging.py             # Logging setup
│           └── validation.py          # Input validation
├── tests/                             # Test suite
│   ├── unit/
│   ├── integration/
│   └── fixtures/
├── docs/                              # Documentation
├── examples/                          # Example configurations
├── scripts/                           # Build and deployment scripts
├── pyproject.toml                     # Project configuration
├── requirements.txt                   # Dependencies
└── README.md                          # Project documentation
```

## Implementation Phases

### Phase 1: Core Foundation (Week 1-2)

#### 1.1 Event System with CloudPathLib Integration

**File: `src/bucket_chat/core/events.py`**
```python
from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, validator
import uuid
import json
from pathlib import Path


class Event(BaseModel):
    """Core event structure for Bucket Chat Protocol"""
    
    event_id: str = Field(..., description="Unique event identifier")
    room_id: str = Field(..., description="Room identifier")
    timestamp_ms: int = Field(..., description="Unix timestamp in milliseconds")
    sender_id: str = Field(..., description="Sender identifier")
    type: str = Field(..., description="Event type")
    parent_event_id: Optional[str] = Field(None, description="Parent event for threading")
    prev_event_hash: Optional[str] = Field(None, description="Hash of previous event by sender")
    signature: str = Field(..., description="Ed25519 signature")
    content: Dict[str, Any] = Field(..., description="Event content")
    
    @classmethod
    def generate_event_id(cls, room_id: str, timestamp_ms: int) -> str:
        """Generate a unique event ID"""
        timestamp_iso = datetime.fromtimestamp(timestamp_ms / 1000).isoformat() + 'Z'
        unique_id = str(uuid.uuid4())
        return f"{room_id}::{timestamp_iso}::{unique_id}"
    
    def to_jsonl_line(self) -> str:
        """Convert event to JSONL line"""
        return self.model_dump_json() + "\n"
    
    @classmethod
    def from_jsonl_line(cls, line: str) -> 'Event':
        """Create event from JSONL line"""
        return cls.model_validate_json(line.strip())


class EventTypes:
    MESSAGE = "m.room.message"
    MEMBER = "m.room.member"
    REDACTION = "m.room.redaction"
    EDIT = "m.room.edit"
    REACTION = "m.room.reaction"
    TYPING = "m.room.typing"
```

#### 1.2 Unified Storage Interface

**File: `src/bucket_chat/core/storage.py`**
```python
from typing import List, Optional, AsyncIterator
from pathlib import Path
import asyncio
import aiofiles
from cloudpathlib import CloudPath, S3Path, GCSPath, AzureBlobPath
from datetime import datetime
import json


class UnifiedStorage:
    """Unified storage interface using cloudpathlib"""
    
    def __init__(self, base_path: str):
        """Initialize with base path (local or cloud)"""
        self.base_path = CloudPath(base_path)
        
    async def ensure_room_structure(self, room_id: str) -> None:
        """Ensure room directory structure exists"""
        room_path = self.base_path / "rooms" / room_id
        logs_path = room_path / "logs"
        
        # Create directories if they don't exist
        room_path.mkdir(parents=True, exist_ok=True)
        logs_path.mkdir(parents=True, exist_ok=True)
        
        # Create metadata.json if it doesn't exist
        metadata_path = room_path / "metadata.json"
        if not metadata_path.exists():
            metadata = {
                "room_id": room_id,
                "created_at": datetime.now().isoformat(),
                "version": "1.0"
            }
            await self.write_json(metadata_path, metadata)
    
    async def write_jsonl_file(self, file_path: CloudPath, events: List[str]) -> bool:
        """Write events to JSONL file"""
        try:
            content = "".join(events)
            if isinstance(file_path, Path):
                # Local file
                async with aiofiles.open(file_path, 'w') as f:
                    await f.write(content)
            else:
                # Cloud file
                file_path.write_text(content)
            return True
        except Exception as e:
            print(f"Error writing JSONL file: {e}")
            return False
    
    async def read_jsonl_file(self, file_path: CloudPath) -> List[str]:
        """Read events from JSONL file"""
        try:
            if isinstance(file_path, Path):
                # Local file
                async with aiofiles.open(file_path, 'r') as f:
                    content = await f.read()
            else:
                # Cloud file
                content = file_path.read_text()
            
            return [line for line in content.split('\n') if line.strip()]
        except Exception as e:
            print(f"Error reading JSONL file: {e}")
            return []
    
    async def list_log_files(self, room_id: str, date: str = None) -> List[CloudPath]:
        """List log files for a room, optionally filtered by date"""
        logs_path = self.base_path / "rooms" / room_id / "logs"
        
        if date:
            date_path = logs_path / date
            if date_path.exists():
                return list(date_path.glob("messages_*.jsonl"))
        else:
            # Get all JSONL files recursively
            files = []
            if logs_path.exists():
                for date_dir in logs_path.iterdir():
                    if date_dir.is_dir():
                        files.extend(date_dir.glob("messages_*.jsonl"))
            return sorted(files)
        
        return []
    
    def get_daily_log_path(self, room_id: str, date: str, 
                          start_ts: int, end_ts: int, client_id: str) -> CloudPath:
        """Get path for daily log file"""
        filename = f"messages_{start_ts}_{end_ts}_{client_id}.jsonl"
        return self.base_path / "rooms" / room_id / "logs" / date / filename
    
    async def write_json(self, file_path: CloudPath, data: dict) -> bool:
        """Write JSON data to file"""
        try:
            content = json.dumps(data, indent=2)
            if isinstance(file_path, Path):
                async with aiofiles.open(file_path, 'w') as f:
                    await f.write(content)
            else:
                file_path.write_text(content)
            return True
        except Exception as e:
            print(f"Error writing JSON file: {e}")
            return False
    
    async def read_json(self, file_path: CloudPath) -> Optional[dict]:
        """Read JSON data from file"""
        try:
            if isinstance(file_path, Path):
                async with aiofiles.open(file_path, 'r') as f:
                    content = await f.read()
            else:
                content = file_path.read_text()
            
            return json.loads(content)
        except Exception as e:
            print(f"Error reading JSON file: {e}")
            return None
```

#### 1.3 OAuth 2.0 Authentication System

**File: `src/bucket_chat/auth/oauth.py`**
```python
from typing import Optional, Dict, Any
import asyncio
import webbrowser
from urllib.parse import urlencode, parse_qs, urlparse
import httpx
from authlib.integrations.httpx_client import AsyncOAuth2Client
import keyring
import json
from datetime import datetime, timedelta


class OAuthProvider:
    """Base OAuth provider configuration"""
    
    def __init__(self, name: str, client_id: str, client_secret: str,
                 auth_url: str, token_url: str, scopes: List[str]):
        self.name = name
        self.client_id = client_id
        self.client_secret = client_secret
        self.auth_url = auth_url
        self.token_url = token_url
        self.scopes = scopes


class OAuthManager:
    """OAuth 2.0 authentication manager"""
    
    def __init__(self, provider: OAuthProvider):
        self.provider = provider
        self.client = AsyncOAuth2Client(
            client_id=provider.client_id,
            client_secret=provider.client_secret
        )
        self.redirect_uri = "http://localhost:8080/callback"
        
    async def start_auth_flow(self) -> str:
        """Start OAuth authorization flow"""
        # Generate authorization URL
        authorization_url, state = self.client.create_authorization_url(
            self.provider.auth_url,
            redirect_uri=self.redirect_uri,
            scope=" ".join(self.provider.scopes)
        )
        
        print(f"Opening browser for authentication...")
        print(f"If browser doesn't open, visit: {authorization_url}")
        
        # Open browser
        webbrowser.open(authorization_url)
        
        # Start local server to handle callback
        callback_code = await self._handle_callback()
        
        if callback_code:
            # Exchange code for token
            token = await self.client.fetch_token(
                self.provider.token_url,
                code=callback_code,
                redirect_uri=self.redirect_uri
            )
            
            # Store token securely
            await self._store_token(token)
            return token['access_token']
        
        raise Exception("Authentication failed")
    
    async def _handle_callback(self) -> Optional[str]:
        """Handle OAuth callback (simplified - would need proper HTTP server)"""
        # In a real implementation, this would start an HTTP server
        # For now, we'll ask user to paste the callback URL
        print("\nAfter authentication, you'll be redirected to localhost:8080")
        print("Copy the full URL from your browser and paste it here:")
        
        callback_url = input("Callback URL: ").strip()
        
        # Parse the callback URL to extract the code
        parsed = urlparse(callback_url)
        query_params = parse_qs(parsed.query)
        
        if 'code' in query_params:
            return query_params['code'][0]
        
        return None
    
    async def _store_token(self, token: dict) -> None:
        """Store token in system keyring"""
        token_data = {
            'access_token': token['access_token'],
            'refresh_token': token.get('refresh_token'),
            'expires_at': (datetime.now() + timedelta(seconds=token.get('expires_in', 3600))).isoformat()
        }
        
        keyring.set_password(
            "bucket-chat", 
            f"{self.provider.name}_token",
            json.dumps(token_data)
        )
    
    async def get_stored_token(self) -> Optional[str]:
        """Get stored token if valid"""
        try:
            token_json = keyring.get_password("bucket-chat", f"{self.provider.name}_token")
            if not token_json:
                return None
                
            token_data = json.loads(token_json)
            expires_at = datetime.fromisoformat(token_data['expires_at'])
            
            if datetime.now() < expires_at:
                return token_data['access_token']
            
            # Token expired, try to refresh
            if token_data.get('refresh_token'):
                return await self._refresh_token(token_data['refresh_token'])
                
        except Exception as e:
            print(f"Error retrieving stored token: {e}")
        
        return None
    
    async def _refresh_token(self, refresh_token: str) -> Optional[str]:
        """Refresh access token"""
        try:
            token = await self.client.refresh_token(
                self.provider.token_url,
                refresh_token=refresh_token
            )
            
            await self._store_token(token)
            return token['access_token']
        except Exception as e:
            print(f"Error refreshing token: {e}")
            return None


# Predefined OAuth providers
class OAuthProviders:
    GOOGLE = OAuthProvider(
        name="google",
        client_id="your-google-client-id",
        client_secret="your-google-client-secret", 
        auth_url="https://accounts.google.com/o/oauth2/v2/auth",
        token_url="https://oauth2.googleapis.com/token",
        scopes=["openid", "email", "profile"]
    )
    
    MICROSOFT = OAuthProvider(
        name="microsoft",
        client_id="your-microsoft-client-id",
        client_secret="your-microsoft-client-secret",
        auth_url="https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
        token_url="https://login.microsoftonline.com/common/oauth2/v2.0/token",
        scopes=["openid", "email", "profile"]
    )
```

### Phase 2: Terminal Client Implementation (Week 3-4)

#### 2.1 Main Client Class

**File: `src/bucket_chat/client/client.py`**
```python
from typing import Optional, List, Dict, Any
import asyncio
from datetime import datetime, date
import uuid

from ..core.events import Event, EventTypes
from ..core.storage import UnifiedStorage
from ..core.crypto import KeyPair, sign_event
from ..auth.oauth import OAuthManager, OAuthProvider
from .buffer import MessageBuffer
from .sync import SyncManager


class BucketChatClient:
    """Main Bucket Chat client"""
    
    def __init__(self, storage_path: str, oauth_provider: OAuthProvider):
        self.storage = UnifiedStorage(storage_path)
        self.oauth_manager = OAuthManager(oauth_provider)
        self.keypair: Optional[KeyPair] = None
        self.user_id: Optional[str] = None
        self.current_room: Optional[str] = None
        self.buffer = MessageBuffer()
        self.sync_manager: Optional[SyncManager] = None
        
    async def authenticate(self) -> bool:
        """Authenticate user with OAuth"""
        # Try to get stored token first
        token = await self.oauth_manager.get_stored_token()
        
        if not token:
            # Start new auth flow
            token = await self.oauth_manager.start_auth_flow()
        
        if token:
            # Get user info and generate/load keypair
            user_info = await self._get_user_info(token)
            self.user_id = user_info.get('email') or user_info.get('sub')
            
            # Load or generate keypair for this user
            self.keypair = await self._load_or_generate_keypair()
            
            return True
        
        return False
    
    async def join_room(self, room_id: str) -> bool:
        """Join a chat room"""
        if not self.user_id or not self.keypair:
            raise Exception("Must authenticate first")
        
        # Ensure room structure exists
        await self.storage.ensure_room_structure(room_id)
        
        # Send join event
        await self._send_member_event(room_id, "join")
        
        self.current_room = room_id
        
        # Start sync manager
        self.sync_manager = SyncManager(self.storage, room_id)
        await self.sync_manager.start()
        
        return True
    
    async def send_message(self, message: str, room_id: str = None) -> bool:
        """Send a message to a room"""
        room_id = room_id or self.current_room
        if not room_id:
            raise Exception("No room specified")
        
        if not self.user_id or not self.keypair:
            raise Exception("Must authenticate first")
        
        # Create message event
        now_ms = int(datetime.now().timestamp() * 1000)
        event_data = {
            "event_id": Event.generate_event_id(room_id, now_ms),
            "room_id": room_id,
            "timestamp_ms": now_ms,
            "sender_id": self.user_id,
            "type": EventTypes.MESSAGE,
            "content": {
                "body": message,
                "msgtype": "m.text"
            }
        }
        
        # Sign event
        signed_event = sign_event(event_data, self.keypair)
        event = Event(**signed_event)
        
        # Buffer the event
        self.buffer.add_event(event)
        
        # Trigger flush if needed
        if self.buffer.should_flush():
            await self._flush_buffer(room_id)
        
        return True
    
    async def get_messages(self, room_id: str, limit: int = 50) -> List[Event]:
        """Get recent messages from a room"""
        # Get recent log files
        log_files = await self.storage.list_log_files(room_id)
        
        events = []
        for file_path in reversed(log_files[-10:]):  # Last 10 files
            lines = await self.storage.read_jsonl_file(file_path)
            for line in lines:
                try:
                    event = Event.from_jsonl_line(line)
                    events.append(event)
                except Exception as e:
                    print(f"Error parsing event: {e}")
        
        # Sort by timestamp and return recent messages
        events.sort(key=lambda e: e.timestamp_ms)
        return events[-limit:]
    
    async def _flush_buffer(self, room_id: str) -> bool:
        """Flush buffered events to storage"""
        events = self.buffer.get_and_clear_events()
        if not events:
            return True
        
        # Group events by date
        events_by_date = {}
        for event in events:
            event_date = date.fromtimestamp(event.timestamp_ms / 1000).isoformat()
            if event_date not in events_by_date:
                events_by_date[event_date] = []
            events_by_date[event_date].append(event)
        
        # Write each date's events to a file
        for event_date, date_events in events_by_date.items():
            start_ts = min(e.timestamp_ms for e in date_events)
            end_ts = max(e.timestamp_ms for e in date_events)
            client_id = self.user_id.split('@')[0] if '@' in self.user_id else self.user_id
            
            file_path = self.storage.get_daily_log_path(
                room_id, event_date, start_ts, end_ts, client_id
            )
            
            jsonl_lines = [event.to_jsonl_line() for event in date_events]
            success = await self.storage.write_jsonl_file(file_path, jsonl_lines)
            
            if not success:
                # Re-buffer events on failure
                for event in date_events:
                    self.buffer.add_event(event)
                return False
        
        return True
    
    async def _send_member_event(self, room_id: str, membership: str):
        """Send a membership event"""
        now_ms = int(datetime.now().timestamp() * 1000)
        event_data = {
            "event_id": Event.generate_event_id(room_id, now_ms),
            "room_id": room_id,
            "timestamp_ms": now_ms,
            "sender_id": self.user_id,
            "type": EventTypes.MEMBER,
            "content": {
                "membership": membership,
                "displayname": self.user_id
            }
        }
        
        signed_event = sign_event(event_data, self.keypair)
        event = Event(**signed_event)
        self.buffer.add_event(event)
        
        await self._flush_buffer(room_id)
```

This reference client implementation provides:

1. **OAuth 2.0 Authentication**: Secure user authentication with token storage
2. **Unified Storage**: Works with local filesystem and cloud storage via `cloudpathlib`
3. **Rich Terminal UI**: Interactive chat interface with real-time updates
4. **Message Buffering**: Efficient batching of events before storage
5. **Real-time Sync**: File system monitoring for new messages
6. **Cross-platform**: Works on Windows, macOS, and Linux

The client serves as a complete reference implementation that demonstrates all aspects of the Bucket Chat Protocol while providing a great user experience in the terminal.