"""
Cryptographic operations for Bucket Chat Protocol

This module provides Ed25519 digital signatures and SHA-256 hash chains
for ensuring message authenticity and tamper detection.
"""

from typing import Optional, Dict, Any
import json
import base64
import hashlib
from datetime import datetime
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.exceptions import InvalidSignature
import keyring


class KeyPair:
    """Ed25519 key pair for signing events"""
    
    def __init__(self, private_key: Optional[Ed25519PrivateKey] = None):
        if private_key is None:
            private_key = Ed25519PrivateKey.generate()
        
        self.private_key = private_key
        self.public_key = private_key.public_key()
    
    def sign(self, data: bytes) -> str:
        """Sign data and return base64 encoded signature"""
        signature = self.private_key.sign(data)
        return base64.b64encode(signature).decode('utf-8')
    
    def verify(self, data: bytes, signature: str) -> bool:
        """Verify signature against data using this keypair's public key"""
        try:
            signature_bytes = base64.b64decode(signature)
            self.public_key.verify(signature_bytes, data)
            return True
        except (InvalidSignature, Exception):
            return False
    
    def public_key_bytes(self) -> bytes:
        """Get public key as raw bytes"""
        return self.public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw
        )
    
    def public_key_base64(self) -> str:
        """Get public key as base64 string"""
        return base64.b64encode(self.public_key_bytes()).decode('utf-8')
    
    def private_key_bytes(self) -> bytes:
        """Get private key as raw bytes"""
        return self.private_key.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption()
        )
    
    def private_key_base64(self) -> str:
        """Get private key as base64 string"""
        return base64.b64encode(self.private_key_bytes()).decode('utf-8')
    
    @classmethod
    def from_private_bytes(cls, private_bytes: bytes) -> 'KeyPair':
        """Create keypair from private key bytes"""
        private_key = Ed25519PrivateKey.from_private_bytes(private_bytes)
        return cls(private_key)
    
    @classmethod
    def from_private_base64(cls, private_base64: str) -> 'KeyPair':
        """Create keypair from base64 encoded private key"""
        private_bytes = base64.b64decode(private_base64)
        return cls.from_private_bytes(private_bytes)
    
    def to_dict(self) -> Dict[str, str]:
        """Export keypair as dictionary"""
        return {
            'public_key': self.public_key_base64(),
            'private_key': self.private_key_base64(),
            'created_at': datetime.now().isoformat()
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, str]) -> 'KeyPair':
        """Import keypair from dictionary"""
        return cls.from_private_base64(data['private_key'])


def verify_signature_with_public_key(data: bytes, signature: str, public_key_bytes: bytes) -> bool:
    """Verify signature against data using provided public key"""
    try:
        public_key = Ed25519PublicKey.from_public_bytes(public_key_bytes)
        signature_bytes = base64.b64decode(signature)
        public_key.verify(signature_bytes, data)
        return True
    except (InvalidSignature, Exception):
        return False


def compute_event_hash(event_dict: Dict[str, Any]) -> str:
    """
    Compute SHA-256 hash of event (excluding signature)
    
    This creates a canonical representation of the event for hash chain purposes.
    """
    # Create copy and remove signature
    event_copy = event_dict.copy()
    event_copy.pop('signature', None)
    
    # Create canonical JSON representation (sorted keys, no spaces)
    canonical_json = json.dumps(event_copy, sort_keys=True, separators=(',', ':'))
    
    # Compute SHA-256 hash
    hash_bytes = hashlib.sha256(canonical_json.encode('utf-8')).digest()
    return base64.b64encode(hash_bytes).decode('utf-8')


def sign_event(event_dict: Dict[str, Any], keypair: KeyPair) -> Dict[str, Any]:
    """
    Sign an event and return the signed event
    
    This function:
    1. Removes any existing signature
    2. Creates canonical JSON representation
    3. Signs the canonical JSON
    4. Adds signature to event
    """
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


def verify_event_signature(event_dict: Dict[str, Any], public_key_bytes: bytes) -> bool:
    """
    Verify an event's signature
    
    Returns True if the signature is valid, False otherwise.
    """
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
        return verify_signature_with_public_key(
            canonical_json.encode('utf-8'),
            signature,
            public_key_bytes
        )
    except Exception:
        return False


def build_hash_chain(events: list[Dict[str, Any]], sender_id: str) -> list[str]:
    """
    Build hash chain for events from a specific sender
    
    Returns list of hashes in chronological order.
    """
    sender_events = [e for e in events if e.get('sender_id') == sender_id]
    sender_events.sort(key=lambda e: e.get('timestamp_ms', 0))
    
    hashes = []
    for event in sender_events:
        event_hash = compute_event_hash(event)
        hashes.append(event_hash)
    
    return hashes


def verify_hash_chain(events: list[Dict[str, Any]], sender_id: str) -> bool:
    """
    Verify hash chain integrity for events from a specific sender
    
    Returns True if the hash chain is valid, False if there are gaps or tampering.
    """
    sender_events = [e for e in events if e.get('sender_id') == sender_id]
    sender_events.sort(key=lambda e: e.get('timestamp_ms', 0))
    
    if not sender_events:
        return True  # Empty chain is valid
    
    prev_hash = None
    for event in sender_events:
        expected_prev_hash = event.get('prev_event_hash')
        
        # First event should have no previous hash
        if prev_hash is None:
            if expected_prev_hash is not None:
                return False
        else:
            # Subsequent events should reference previous hash
            if expected_prev_hash != prev_hash:
                return False
        
        # Compute current event hash for next iteration
        prev_hash = compute_event_hash(event)
    
    return True


class KeyManager:
    """Manages user keypairs with secure storage"""
    
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.service_name = "bucket-chat"
        self.key_name = f"keypair_{user_id}"
    
    def save_keypair(self, keypair: KeyPair) -> bool:
        """Save keypair to secure storage"""
        try:
            keypair_data = keypair.to_dict()
            keypair_json = json.dumps(keypair_data)
            keyring.set_password(self.service_name, self.key_name, keypair_json)
            return True
        except Exception as e:
            print(f"Error saving keypair: {e}")
            return False
    
    def load_keypair(self) -> Optional[KeyPair]:
        """Load keypair from secure storage"""
        try:
            keypair_json = keyring.get_password(self.service_name, self.key_name)
            if not keypair_json:
                return None
            
            keypair_data = json.loads(keypair_json)
            return KeyPair.from_dict(keypair_data)
        except Exception as e:
            print(f"Error loading keypair: {e}")
            return None
    
    def generate_and_save_keypair(self) -> KeyPair:
        """Generate new keypair and save it"""
        keypair = KeyPair()
        self.save_keypair(keypair)
        return keypair
    
    def get_or_create_keypair(self) -> KeyPair:
        """Get existing keypair or create new one"""
        keypair = self.load_keypair()
        if keypair is None:
            keypair = self.generate_and_save_keypair()
        return keypair
    
    def delete_keypair(self) -> bool:
        """Delete keypair from secure storage"""
        try:
            keyring.delete_password(self.service_name, self.key_name)
            return True
        except Exception as e:
            print(f"Error deleting keypair: {e}")
            return False


# Utility functions for testing and development
def generate_test_keypair() -> KeyPair:
    """Generate a keypair for testing purposes"""
    return KeyPair()


def create_test_event(room_id: str, sender_id: str, message: str, keypair: KeyPair) -> Dict[str, Any]:
    """Create a test event with proper signature"""
    from datetime import datetime
    import uuid
    
    now_ms = int(datetime.now().timestamp() * 1000)
    event_data = {
        "event_id": f"{room_id}::{datetime.now().isoformat()}Z::{uuid.uuid4()}",
        "room_id": room_id,
        "timestamp_ms": now_ms,
        "sender_id": sender_id,
        "type": "m.room.message",
        "content": {
            "body": message,
            "msgtype": "m.text"
        }
    }
    
    return sign_event(event_data, keypair)


if __name__ == "__main__":
    # Simple test
    print("Testing Bucket Chat cryptographic functions...")
    
    # Generate keypair
    keypair = generate_test_keypair()
    print(f"Generated keypair with public key: {keypair.public_key_base64()[:16]}...")
    
    # Create and sign test event
    test_event = create_test_event("test_room", "alice@example.com", "Hello, World!", keypair)
    print(f"Created signed event: {test_event['event_id']}")
    
    # Verify signature
    is_valid = verify_event_signature(test_event, keypair.public_key_bytes())
    print(f"Signature verification: {'✅ VALID' if is_valid else '❌ INVALID'}")
    
    # Test hash computation
    event_hash = compute_event_hash(test_event)
    print(f"Event hash: {event_hash[:16]}...")
    
    print("✅ All cryptographic tests passed!")