"""
Bucket Chat - Reference Implementation

A decentralized, serverless chat system that leverages cloud object storage
for persistence and security. This is the reference implementation of the
Bucket Chat Protocol v1.0.

Key Features:
- Decentralized architecture with no central servers
- Cryptographic security with Ed25519 signatures and hash chains
- Unified storage interface supporting local and cloud storage
- OAuth 2.0 authentication support
- Rich terminal-based user interface
- Cross-platform compatibility

Usage:
    from bucket_chat import BucketChatClient
    
    client = BucketChatClient("./chat-data", "alice@example.com")
    await client.initialize()
    await client.join_room("general")
    await client.send_message("Hello, World!")
"""

__version__ = "0.1.0"
__author__ = "Bucket Chat Contributors"
__license__ = "AGPLv3"

# Core imports
from .core import Event, EventTypes, KeyPair, KeyManager, UnifiedStorage
from .client.client import BucketChatClient
from .auth import SimpleAuth

__all__ = [
    'Event',
    'EventTypes',
    'KeyPair', 
    'KeyManager',
    'UnifiedStorage',
    'BucketChatClient',
    'SimpleAuth'
]