# Bucket Chat - Reference Implementation

A decentralized, serverless chat system that leverages cloud object storage for persistence and security. This is the reference implementation of the Bucket Chat Protocol v1.0.

## 🌟 Key Features

- **Decentralized**: No central servers, databases, or daemons required
- **Secure**: Ed25519 signatures and SHA-256 hash chains prevent forgery and tampering
- **Cloud-Agnostic**: Works with local filesystem, AWS S3, Google Cloud Storage, Azure Blob Storage
- **Immutable**: Write-once storage policies ensure message history cannot be altered
- **Real-time**: File system monitoring and optional event notifications for live updates
- **Cross-platform**: Runs on Windows, macOS, and Linux

## 🚀 Quick Start

### Installation

```bash
# Clone the repository
git clone <repository-url>
cd bucket-chat

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install in development mode
pip install -e .
```

### Basic Usage

1. **Test the cryptographic functions:**
```bash
bucket-chat test-crypto
```

2. **Test storage operations:**
```bash
bucket-chat test-storage --room-id my-room
```

3. **Set up your user keys:**
```bash
bucket-chat setup-keys --user-id alice@example.com
```

4. **Start chatting:**
```bash
bucket-chat chat --room-id general --user-id alice@example.com
```

5. **View chat history:**
```bash
bucket-chat history --room-id general
```

### Storage Configurations

The client supports multiple storage backends:

```bash
# Local filesystem (default)
bucket-chat chat -s ./my-chat-data

# AWS S3
bucket-chat chat -s s3://my-bucket/chat-data

# Google Cloud Storage  
bucket-chat chat -s gs://my-bucket/chat-data

# Azure Blob Storage
bucket-chat chat -s az://my-container/chat-data
```

## 📁 How It Works

### File Structure

```
storage-path/
├── rooms/
│   └── room-id/
│       ├── metadata.json
│       └── logs/
│           └── YYYY-MM-DD/
│               ├── messages_start_end_client.jsonl
│               └── messages_start_end_client.jsonl
```

### Event Format

Each message is stored as a signed JSON event:

```json
{
  "event_id": "room_123::2025-09-14T12:00:00.123Z::uuid4",
  "room_id": "room_123",
  "timestamp_ms": 1726315200123,
  "sender_id": "alice@example.com",
  "type": "m.room.message",
  "parent_event_id": null,
  "prev_event_hash": "sha256_hash_of_previous_event",
  "signature": "base64_ed25519_signature",
  "content": {
    "body": "Hello, World!",
    "msgtype": "m.text"
  }
}
```

### Security Model

- **Authentication**: Ed25519 digital signatures on all events
- **Integrity**: SHA-256 hash chains detect tampering
- **Immutability**: Storage policies prevent modification/deletion
- **Non-repudiation**: Signatures prove authorship

## 🛠️ Development

### Project Structure

```
src/bucket_chat/
├── core/                   # Core protocol implementation
│   ├── events.py          # Event schema and validation
│   ├── crypto.py          # Cryptographic operations
│   └── storage.py         # Unified storage interface
├── client/                # Client implementation
│   └── client.py          # Main client class
├── auth/                  # Authentication (OAuth 2.0 planned)
├── cli/                   # Command-line interface
│   └── main.py            # CLI entry point
└── __init__.py            # Package exports
```

### Running Tests

```bash
# Test cryptographic functions
python -m bucket_chat.core.crypto

# Test event system
python -m bucket_chat.core.events

# Test storage system
python -m bucket_chat.core.storage

# Test client
python -m bucket_chat.client.client
```

### Code Quality

```bash
# Format code
black src/ tests/

# Type checking
mypy src/

# Run tests
pytest tests/
```

## 🔮 Roadmap

### Current Status (v0.1.0)
- ✅ Core protocol implementation
- ✅ Cryptographic security (Ed25519 + SHA-256)
- ✅ Unified storage interface (local + cloud)
- ✅ Basic terminal client
- ✅ Message sending and history

### Planned Features (v0.2.0)
- [ ] OAuth 2.0 authentication
- [ ] Real-time synchronization
- [ ] Message threading
- [ ] File attachments
- [ ] Message reactions
- [ ] Rich terminal UI with Textual

### Future Enhancements (v1.0.0)
- [ ] Web client
- [ ] Mobile clients
- [ ] End-to-end encryption
- [ ] Advanced room management
- [ ] Federation support

## 📖 Protocol Specification

For the complete protocol specification, see [specification.md](specification.md).

For implementation details, see:
- [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md)
- [TECHNICAL_ARCHITECTURE.md](TECHNICAL_ARCHITECTURE.md)
- [PROJECT_ROADMAP.md](PROJECT_ROADMAP.md)

## 🤝 Contributing

We welcome contributions! Please see our contributing guidelines for details.

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

## 📄 License

This project is licensed under the GNU Affero General Public License v3.0 (AGPLv3). See [LICENSE](LICENSE) for details.

## 🆘 Support

- **Issues**: Report bugs and request features on GitHub Issues
- **Discussions**: Join discussions on GitHub Discussions
- **Documentation**: Read the full documentation at [docs/](docs/)

---

**Bucket Chat** - Decentralized chat for the modern world 🚀