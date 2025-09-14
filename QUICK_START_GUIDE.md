# Bucket Chat Protocol - Quick Start Guide

## Overview

This guide helps developers get started with implementing the Bucket Chat Protocol. It provides step-by-step instructions for setting up a development environment and creating your first working implementation.

## Prerequisites

### Required Software
- Python 3.9 or higher
- Node.js 18+ (for web client)
- Git
- Docker (for testing with MinIO)

### Cloud Storage Access
At least one of the following:
- AWS S3 account with programmatic access
- Google Cloud Storage account with service account
- Local MinIO installation (for development)

### Development Tools (Recommended)
- VS Code or PyCharm
- Postman or similar API testing tool
- Git client

## Development Environment Setup

### 1. Repository Structure Setup

Create the initial project structure:

```bash
mkdir bucket-chat
cd bucket-chat

# Create directory structure
mkdir -p core/{events,crypto,storage,client}
mkdir -p cli
mkdir -p web/src/{components,services,utils}
mkdir -p tests/{unit,integration,e2e}
mkdir -p docs
mkdir -p examples
mkdir -p tools
```

### 2. Python Environment Setup

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Create requirements.txt
cat > requirements.txt << EOF
# Core dependencies
cryptography>=41.0.0
boto3>=1.28.0
google-cloud-storage>=2.10.0
minio>=7.1.0
click>=8.1.0
pydantic>=2.0.0
python-json-logger>=2.0.0

# Development dependencies
pytest>=7.4.0
pytest-cov>=4.1.0
pytest-asyncio>=0.21.0
black>=23.0.0
flake8>=6.0.0
mypy>=1.5.0

# Web server dependencies (optional)
fastapi>=0.103.0
uvicorn>=0.23.0
websockets>=11.0.0
EOF

# Install dependencies
pip install -r requirements.txt
```

### 3. MinIO Setup (for local development)

```bash
# Using Docker
docker run -p 9000:9000 -p 9001:9001 \
  -e "MINIO_ROOT_USER=minioadmin" \
  -e "MINIO_ROOT_PASSWORD=minioadmin" \
  minio/minio server /data --console-address ":9001"
```

Access MinIO console at http://localhost:9001 (admin/minioadmin)

## Phase 1: Core Implementation

### Step 1: Event System Implementation

Create `core/events/schema.py`:

```python
from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
import uuid
import json


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
    
    def to_json(self) -> str:
        """Convert event to JSON string"""
        return self.model_dump_json()
    
    @classmethod
    def from_json(cls, json_str: str) -> 'Event':
        """Create event from JSON string"""
        return cls.model_validate_json(json_str)


# Event type constants
class EventTypes:
    MESSAGE = "m.room.message"
    MEMBER = "m.room.member"
    REDACTION = "m.room.redaction"
    EDIT = "m.room.edit"
    REACTION = "m.room.reaction"
    TYPING = "m.room.typing"


class MessageContent(BaseModel):
    """Content for m.room.message events"""
    body: str
    msgtype: str = "m.text"


class MemberContent(BaseModel):
    """Content for m.room.member events"""
    membership: str  # "join", "leave", "invite", "ban"
    displayname: Optional[str] = None
```

Create `core/events/__init__.py`:

```python
from .schema import Event, EventTypes, MessageContent, MemberContent

__all__ = ['Event', 'EventTypes', 'MessageContent', 'MemberContent']
```

### Step 2: Basic Cryptographic Implementation

Create `core/crypto/signatures.py`:

```python
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.exceptions import InvalidSignature
import base64
import hashlib
import json
from typing import Tuple


class KeyPair:
    """Ed25519 key pair for signing events"""
    
    def __init__(self, private_key: Ed25519PrivateKey = None):
        if private_key is None:
            private_key = Ed25519PrivateKey.generate()
        
        self.private_key = private_key
        self.public_key = private_key.public_key()
    
    def sign(self, data: bytes) -> str:
        """Sign data and return base64 encoded signature"""
        signature = self.private_key.sign(data)
        return base64.b64encode(signature).decode('utf-8')
    
    def verify(self, data: bytes, signature: str) -> bool:
        """Verify signature against data"""
        try:
            signature_bytes = base64.b64decode(signature)
            self.public_key.verify(signature_bytes, data)
            return True
        except (InvalidSignature, Exception):
            return False
    
    def public_key_bytes(self) -> bytes:
        """Get public key as bytes"""
        return self.public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw
        )
    
    def private_key_bytes(self) -> bytes:
        """Get private key as bytes"""
        return self.private_key.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption()
        )
    
    @classmethod
    def from_private_bytes(cls, private_bytes: bytes) -> 'KeyPair':
        """Create keypair from private key bytes"""
        private_key = Ed25519PrivateKey.from_private_bytes(private_bytes)
        return cls(private_key)


def compute_event_hash(event_dict: dict) -> str:
    """Compute SHA-256 hash of event (excluding signature)"""
    # Create copy and remove signature
    event_copy = event_dict.copy()
    event_copy.pop('signature', None)
    
    # Create canonical JSON representation
    canonical_json = json.dumps(event_copy, sort_keys=True, separators=(',', ':'))
    
    # Compute hash
    hash_bytes = hashlib.sha256(canonical_json.encode('utf-8')).digest()
    return base64.b64encode(hash_bytes).decode('utf-8')


def sign_event(event_dict: dict, keypair: KeyPair) -> dict:
    """Sign an event and return the signed event"""
    # Remove existing signature
    event_copy = event_dict.copy()
    event_copy.pop('signature', None)
    
    # Create canonical JSON for signing
    canonical_json = json.dumps(event_copy, sort_keys=True, separators=(',', ':'))
    
    # Sign the canonical JSON
    signature = keypair.sign(canonical_json.encode('utf-8'))
    
    # Add signature to event
    event_copy['signature'] = signature
    return event_copy


def verify_event_signature(event_dict: dict, public_key_bytes: bytes) -> bool:
    """Verify an event's signature"""
    try:
        # Extract signature
        signature = event_dict.get('signature')
        if not signature:
            return False
        
        # Remove signature for verification
        event_copy = event_dict.copy()
        event_copy.pop('signature')
        
        # Create canonical JSON
        canonical_json = json.dumps(event_copy, sort_keys=True, separators=(',', ':'))
        
        # Verify signature
        public_key = Ed25519PublicKey.from_public_bytes(public_key_bytes)
        signature_bytes = base64.b64decode(signature)
        public_key.verify(signature_bytes, canonical_json.encode('utf-8'))
        return True
    except Exception:
        return False
```

### Step 3: Basic Storage Implementation

Create `core/storage/interface.py`:

```python
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
import asyncio


class StorageInterface(ABC):
    """Abstract interface for cloud storage providers"""
    
    @abstractmethod
    async def upload_file(self, path: str, content: bytes, metadata: Dict[str, str] = None) -> bool:
        """Upload file to storage"""
        pass
    
    @abstractmethod
    async def download_file(self, path: str) -> Optional[bytes]:
        """Download file from storage"""
        pass
    
    @abstractmethod
    async def list_files(self, prefix: str) -> List[str]:
        """List files with given prefix"""
        pass
    
    @abstractmethod
    async def file_exists(self, path: str) -> bool:
        """Check if file exists"""
        pass
    
    @abstractmethod
    async def get_file_metadata(self, path: str) -> Optional[Dict[str, Any]]:
        """Get file metadata"""
        pass
    
    @abstractmethod
    async def delete_file(self, path: str) -> bool:
        """Delete file (should be restricted in production)"""
        pass


class StorageError(Exception):
    """Base exception for storage operations"""
    pass


class FileNotFoundError(StorageError):
    """File not found in storage"""
    pass


class AccessDeniedError(StorageError):
    """Access denied to storage resource"""
    pass
```

Create `core/storage/minio.py`:

```python
from minio import Minio
from minio.error import S3Error
from .interface import StorageInterface, StorageError, FileNotFoundError, AccessDeniedError
from typing import List, Optional, Dict, Any
import io
import asyncio


class MinIOStorage(StorageInterface):
    """MinIO storage implementation"""
    
    def __init__(self, endpoint: str, access_key: str, secret_key: str, 
                 bucket_name: str, secure: bool = False):
        self.client = Minio(
            endpoint=endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure
        )
        self.bucket_name = bucket_name
        self._ensure_bucket()
    
    def _ensure_bucket(self):
        """Ensure bucket exists"""
        if not self.client.bucket_exists(self.bucket_name):
            self.client.make_bucket(self.bucket_name)
    
    async def upload_file(self, path: str, content: bytes, metadata: Dict[str, str] = None) -> bool:
        """Upload file to MinIO"""
        try:
            data = io.BytesIO(content)
            self.client.put_object(
                self.bucket_name,
                path,
                data,
                length=len(content),
                metadata=metadata or {}
            )
            return True
        except S3Error as e:
            if e.code == 'AccessDenied':
                raise AccessDeniedError(f"Access denied: {e}")
            raise StorageError(f"Upload failed: {e}")
    
    async def download_file(self, path: str) -> Optional[bytes]:
        """Download file from MinIO"""
        try:
            response = self.client.get_object(self.bucket_name, path)
            data = response.read()
            response.close()
            response.release_conn()
            return data
        except S3Error as e:
            if e.code == 'NoSuchKey':
                raise FileNotFoundError(f"File not found: {path}")
            if e.code == 'AccessDenied':
                raise AccessDeniedError(f"Access denied: {e}")
            raise StorageError(f"Download failed: {e}")
    
    async def list_files(self, prefix: str) -> List[str]:
        """List files with prefix"""
        try:
            objects = self.client.list_objects(self.bucket_name, prefix=prefix, recursive=True)
            return [obj.object_name for obj in objects]
        except S3Error as e:
            raise StorageError(f"List failed: {e}")
    
    async def file_exists(self, path: str) -> bool:
        """Check if file exists"""
        try:
            self.client.stat_object(self.bucket_name, path)
            return True
        except S3Error as e:
            if e.code == 'NoSuchKey':
                return False
            raise StorageError(f"Stat failed: {e}")
    
    async def get_file_metadata(self, path: str) -> Optional[Dict[str, Any]]:
        """Get file metadata"""
        try:
            stat = self.client.stat_object(self.bucket_name, path)
            return {
                'size': stat.size,
                'last_modified': stat.last_modified,
                'etag': stat.etag,
                'content_type': stat.content_type,
                'metadata': stat.metadata
            }
        except S3Error as e:
            if e.code == 'NoSuchKey':
                return None
            raise StorageError(f"Get metadata failed: {e}")
    
    async def delete_file(self, path: str) -> bool:
        """Delete file"""
        try:
            self.client.remove_object(self.bucket_name, path)
            return True
        except S3Error as e:
            if e.code == 'NoSuchKey':
                return False
            raise StorageError(f"Delete failed: {e}")
```

### Step 4: Basic Testing

Create `tests/unit/test_events.py`:

```python
import pytest
from datetime import datetime
from core.events import Event, EventTypes, MessageContent


def test_event_creation():
    """Test basic event creation"""
    event_data = {
        "event_id": "room_test::2025-09-14T12:00:00.000Z::test-uuid",
        "room_id": "room_test",
        "timestamp_ms": 1726315200000,
        "sender_id": "user:alice",
        "type": EventTypes.MESSAGE,
        "signature": "test_signature",
        "content": {"body": "Hello, World!", "msgtype": "m.text"}
    }
    
    event = Event(**event_data)
    assert event.room_id == "room_test"
    assert event.sender_id == "user:alice"
    assert event.type == EventTypes.MESSAGE


def test_event_id_generation():
    """Test event ID generation"""
    room_id = "room_test"
    timestamp_ms = 1726315200000
    
    event_id = Event.generate_event_id(room_id, timestamp_ms)
    
    assert event_id.startswith(f"{room_id}::")
    assert "2025-09-14T12:00:00" in event_id


def test_event_json_serialization():
    """Test event JSON serialization/deserialization"""
    event_data = {
        "event_id": "room_test::2025-09-14T12:00:00.000Z::test-uuid",
        "room_id": "room_test",
        "timestamp_ms": 1726315200000,
        "sender_id": "user:alice",
        "type": EventTypes.MESSAGE,
        "signature": "test_signature",
        "content": {"body": "Hello, World!", "msgtype": "m.text"}
    }
    
    event = Event(**event_data)
    json_str = event.to_json()
    
    # Deserialize back
    event2 = Event.from_json(json_str)
    assert event2.room_id == event.room_id
    assert event2.content == event.content


if __name__ == "__main__":
    pytest.main([__file__])
```

### Step 5: Simple CLI for Testing

Create `cli/simple_test.py`:

```python
#!/usr/bin/env python3
"""
Simple CLI for testing Bucket Chat Protocol implementation
"""

import asyncio
import json
from datetime import datetime
from core.events import Event, EventTypes, MessageContent
from core.crypto.signatures import KeyPair, sign_event
from core.storage.minio import MinIOStorage


async def main():
    print("Bucket Chat Protocol - Simple Test")
    print("=" * 40)
    
    # Initialize storage (MinIO for testing)
    storage = MinIOStorage(
        endpoint="localhost:9000",
        access_key="minioadmin",
        secret_key="minioadmin",
        bucket_name="bucket-chat-test",
        secure=False
    )
    
    # Generate test keypair
    keypair = KeyPair()
    print(f"Generated keypair for testing")
    
    # Create test event
    now_ms = int(datetime.now().timestamp() * 1000)
    room_id = "room_test"
    
    event_data = {
        "event_id": Event.generate_event_id(room_id, now_ms),
        "room_id": room_id,
        "timestamp_ms": now_ms,
        "sender_id": "user:alice",
        "type": EventTypes.MESSAGE,
        "content": {"body": "Hello, Bucket Chat!", "msgtype": "m.text"}
    }
    
    # Sign the event
    signed_event = sign_event(event_data, keypair)
    event = Event(**signed_event)
    
    print(f"Created event: {event.event_id}")
    print(f"Message: {event.content['body']}")
    
    # Create JSONL content
    jsonl_content = event.to_json() + "\n"
    
    # Upload to storage
    file_path = f"rooms/{room_id}/logs/2025-09-14/messages_{now_ms}_{now_ms}_alice.jsonl"
    success = await storage.upload_file(file_path, jsonl_content.encode('utf-8'))
    
    if success:
        print(f"✅ Successfully uploaded to: {file_path}")
        
        # Download and verify
        downloaded = await storage.download_file(file_path)
        if downloaded:
            downloaded_event = Event.from_json(downloaded.decode('utf-8').strip())
            print(f"✅ Successfully downloaded and parsed event")
            print(f"   Event ID: {downloaded_event.event_id}")
            print(f"   Message: {downloaded_event.content['body']}")
        else:
            print("❌ Failed to download file")
    else:
        print("❌ Failed to upload file")


if __name__ == "__main__":
    asyncio.run(main())
```

## Running the First Test

1. **Start MinIO** (if not already running):
```bash
docker run -p 9000:9000 -p 9001:9001 \
  -e "MINIO_ROOT_USER=minioadmin" \
  -e "MINIO_ROOT_PASSWORD=minioadmin" \
  minio/minio server /data --console-address ":9001"
```

2. **Run the simple test**:
```bash
cd bucket-chat
python cli/simple_test.py
```

Expected output:
```
Bucket Chat Protocol - Simple Test
========================================
Generated keypair for testing
Created event: room_test::2025-09-14T12:00:00.123Z::abc-123-def
Message: Hello, Bucket Chat!
✅ Successfully uploaded to: rooms/room_test/logs/2025-09-14/messages_1726315200123_1726315200123_alice.jsonl
✅ Successfully downloaded and parsed event
   Event ID: room_test::2025-09-14T12:00:00.123Z::abc-123-def
   Message: Hello, Bucket Chat!
```

## Next Steps

After completing this quick start:

1. **Run the unit tests**: `pytest tests/unit/`
2. **Implement AWS S3 storage**: Follow the MinIO pattern
3. **Add signature verification**: Extend the crypto module
4. **Build the client library**: Implement buffering and timeline reconstruction
5. **Create a proper CLI**: Interactive chat interface

## Common Issues and Solutions

### MinIO Connection Issues
- Ensure Docker is running and MinIO container is started
- Check that ports 9000 and 9001 are not in use
- Verify MinIO credentials (minioadmin/minioadmin)

### Import Errors
- Ensure virtual environment is activated
- Install all requirements: `pip install -r requirements.txt`
- Check Python path and module structure

### Storage Permission Issues
- MinIO should work out of the box for testing
- For AWS/GCS, ensure proper credentials and permissions
- Check bucket policies and IAM settings

## Development Tips

1. **Use type hints**: All code should include proper type annotations
2. **Write tests first**: Follow TDD principles for core functionality
3. **Handle errors gracefully**: Use proper exception handling
4. **Log operations**: Add structured logging for debugging
5. **Document everything**: Include docstrings and comments

This quick start guide provides a foundation for implementing the Bucket Chat Protocol. Follow the full implementation plan and technical architecture for a complete system.