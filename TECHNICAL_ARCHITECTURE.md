# Bucket Chat Protocol - Technical Architecture

## Architecture Overview

The Bucket Chat Protocol implementation follows a layered architecture designed for modularity, testability, and cloud-agnostic operation. The system is built around immutable event logs stored in cloud object storage, with cryptographic security ensuring data integrity.

## System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    User Interfaces                         │
├─────────────────────┬───────────────────────────────────────┤
│   CLI Application   │        Web Client (React)            │
│   - Interactive     │        - Real-time UI                │
│   - Commands        │        - File uploads                │
│   - Configuration   │        - Notifications               │
└─────────────────────┴───────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                  Client Library Layer                      │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │   Buffer    │  │ Timeline    │  │   Synchronization   │  │
│  │  Manager    │  │ Manager     │  │      Manager        │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │    Room     │  │   State     │  │     Metadata        │  │
│  │  Manager    │  │ Resolver    │  │     Manager         │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                   Core Protocol Layer                      │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │   Event     │  │ Crypto      │  │      Storage        │  │
│  │  System     │  │ Security    │  │    Abstraction      │  │
│  │             │  │             │  │                     │  │
│  │ - Schema    │  │ - Ed25519   │  │ - Multi-cloud       │  │
│  │ - Validation│  │ - Hash Chain│  │ - File naming       │  │
│  │ - Generation│  │ - Verify    │  │ - Immutability      │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                Cloud Storage Providers                     │
├─────────────────────┬──────────────────┬──────────────────────┤
│     AWS S3          │   Google Cloud   │       MinIO          │
│   - Object Lock     │     Storage      │   - Self-hosted      │
│   - Event Notify    │   - Bucket Lock  │   - S3 Compatible    │
│   - IAM Policies    │   - Pub/Sub      │   - Local Testing    │
└─────────────────────┴──────────────────┴──────────────────────┘
```

## Core Components

### 1. Event System

The event system is the foundation of the protocol, handling all message and state changes as immutable events.

#### Event Schema Structure
```python
class Event:
    event_id: str           # Unique identifier
    room_id: str           # Room identifier  
    timestamp_ms: int      # Unix timestamp in milliseconds
    sender_id: str         # User identifier
    type: str              # Event type (m.room.message, etc.)
    parent_event_id: str   # For threading (optional)
    prev_event_hash: str   # Hash of previous event by sender
    signature: str         # Ed25519 signature
    content: dict          # Event-specific payload
```

#### Event Types
- **m.room.message**: Standard text messages
- **m.room.member**: Membership changes (join/leave/invite)
- **m.room.redaction**: Message deletions
- **m.room.edit**: Message edits (creates new event)
- **m.room.reaction**: Emoji reactions
- **m.room.typing**: Typing indicators (ephemeral, not stored)

#### Event ID Generation
Format: `{room_id}::{ISO8601_timestamp}::{uuid4}`
Example: `room_abc123::20250914T120045.123Z::550e8400-e29b-41d4-a716-446655440000`

### 2. Cryptographic Security

#### Ed25519 Digital Signatures
- Each event is signed by the sender's private key
- Signatures prevent forgery and ensure authenticity
- Public keys are distributed through room metadata

#### Hash Chain Implementation
- Each event includes the hash of the sender's previous event
- Creates a tamper-evident chain for each sender
- SHA-256 hashing algorithm
- Broken chains indicate tampering

#### Key Management
```python
class UserKeys:
    private_key: bytes     # Ed25519 private key
    public_key: bytes      # Ed25519 public key
    user_id: str          # Associated user identifier
    created_at: datetime   # Key creation timestamp
```

### 3. Storage Layer Architecture

#### File Structure
```
/rooms/{room_id}/
    metadata.json                           # Room configuration
    logs/
        2025-09-14/
            messages_1726315200000_1726315800000_alice.jsonl
            messages_1726315800000_1726316400000_bob.jsonl
        2025-09-15/
            messages_1726401600000_1726402200000_alice.jsonl
```

#### File Naming Convention
Format: `messages_{start_ts}_{end_ts}_{client_id}.jsonl`
- `start_ts`: Unix timestamp (ms) of first event
- `end_ts`: Unix timestamp (ms) of last event
- `client_id`: Identifier of the client that created the file

#### Storage Provider Abstraction
```python
class StorageInterface:
    async def upload_file(self, path: str, content: bytes) -> bool
    async def download_file(self, path: str) -> bytes
    async def list_files(self, prefix: str) -> List[str]
    async def file_exists(self, path: str) -> bool
    async def get_file_metadata(self, path: str) -> dict
```

### 4. Client Library Architecture

#### Buffer Manager
- Collects events locally before writing to storage
- Configurable flush intervals (default: 5-10 seconds)
- Handles batching for optimal storage performance
- Ensures atomic writes to prevent partial files

#### Timeline Manager
- Reconstructs chronological event order
- Merges events from multiple JSONL files
- Handles out-of-order delivery
- Maintains event ordering by timestamp

#### State Resolver
- Processes events to determine current room state
- Handles membership changes
- Resolves conflicts in concurrent operations
- Maintains current room metadata

#### Synchronization Manager
- Monitors storage for new files
- Handles real-time updates via storage events
- Implements fallback polling mechanisms
- Manages last-seen event tracking

## Data Flow

### Message Sending Flow
1. User composes message in client
2. Client creates event with signature and hash chain
3. Event is buffered locally
4. Buffer is periodically flushed to JSONL file
5. File is uploaded to storage with immutable policy
6. Storage triggers event notification
7. Other clients receive notification and download new file
8. Clients verify signatures and update timeline

### Message Receiving Flow
1. Client receives storage event notification (or polls)
2. Client downloads new JSONL files
3. Events are extracted and validated
4. Signatures are verified using sender's public key
5. Hash chains are validated for integrity
6. Events are merged into timeline
7. Room state is updated
8. UI is refreshed with new messages

## Security Model

### Threat Model
- **Malicious Storage Provider**: Cannot forge or modify events due to signatures
- **Man-in-the-Middle**: Cannot inject events without valid signatures
- **Compromised Client**: Can only create events as authenticated user
- **Storage Tampering**: Detected through hash chain verification

### Security Controls
1. **Authentication**: Ed25519 signatures on all events
2. **Integrity**: SHA-256 hash chains detect tampering
3. **Non-repudiation**: Signatures prevent denial of authorship
4. **Immutability**: Storage policies prevent modification/deletion
5. **Access Control**: Bucket permissions limit read/write access

## Performance Considerations

### Scalability Targets
- **Room Size**: 1000+ concurrent participants
- **Message Rate**: 100+ messages per minute per room
- **History Size**: Unlimited (cloud storage scales)
- **Latency**: < 1 second for message delivery
- **Throughput**: 10,000+ events per second per client

### Optimization Strategies
1. **Batching**: Group events into files to reduce storage operations
2. **Caching**: Cache recent events and room state locally
3. **Indexing**: Maintain local indexes for fast message lookup
4. **Compression**: Compress JSONL files for storage efficiency
5. **Pagination**: Load message history in chunks

### Resource Usage
- **Storage**: ~1KB per message (including metadata)
- **Bandwidth**: ~100KB/minute for active chat room
- **CPU**: Minimal (mainly crypto operations)
- **Memory**: ~10MB for typical client session

## Fault Tolerance

### Error Handling
- **Network Failures**: Retry with exponential backoff
- **Storage Unavailable**: Queue operations locally
- **Corrupt Files**: Skip and report errors
- **Invalid Events**: Reject and continue processing
- **Signature Failures**: Mark as unverified, alert user

### Recovery Mechanisms
- **Timeline Reconstruction**: Rebuild from all available files
- **State Recovery**: Recompute from event history
- **Missing Events**: Request retransmission from peers
- **Conflict Resolution**: Use timestamp-based ordering

## Monitoring and Observability

### Metrics to Track
- Event processing rate
- Storage operation latency
- Signature verification time
- Timeline reconstruction duration
- Error rates by type

### Logging Strategy
- Structured JSON logs
- Event-level audit trail
- Security event logging
- Performance metrics
- Error tracking with context

## Development and Testing

### Testing Strategy
1. **Unit Tests**: Individual component functionality
2. **Integration Tests**: Cross-component interactions
3. **End-to-End Tests**: Complete user workflows
4. **Security Tests**: Cryptographic verification
5. **Performance Tests**: Load and stress testing
6. **Compatibility Tests**: Multi-cloud and multi-client

### Development Environment
- Local MinIO for storage testing
- Docker containers for isolated testing
- Mock storage providers for unit tests
- Test key generation utilities
- Automated CI/CD pipeline

This technical architecture provides the foundation for implementing a robust, secure, and scalable decentralized chat system that fulfills all requirements of the Bucket Chat Protocol specification.