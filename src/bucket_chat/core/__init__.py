"""
Bucket Chat Core Module

This module contains the core protocol implementation including:
- Event schema and validation
- Cryptographic operations (Ed25519 signatures, hash chains)
- Unified storage interface (local and cloud)
- Timeline reconstruction
"""

from .events import Event, EventTypes
from .crypto import KeyPair, KeyManager, sign_event, verify_event_signature, compute_event_hash
from .storage import UnifiedStorage

__all__ = [
    'Event',
    'EventTypes', 
    'KeyPair',
    'KeyManager',
    'sign_event',
    'verify_event_signature',
    'compute_event_hash',
    'UnifiedStorage'
]