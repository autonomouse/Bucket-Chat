"""
Unified Storage Interface for Bucket Chat Protocol

This module provides a unified interface for both local filesystem and
cloud storage operations using cloudpathlib. It handles the file structure
and naming conventions defined in the protocol specification.
"""

from typing import List, Optional, AsyncIterator, Union
from pathlib import Path
import asyncio
import json
from datetime import datetime, date

try:
    import aiofiles
    from cloudpathlib import CloudPath, S3Path, GCSPath, AzureBlobPath
    CLOUD_AVAILABLE = True
except ImportError:
    CLOUD_AVAILABLE = False
    # Fallback for basic local file operations
    CloudPath = Path


class StorageError(Exception):
    """Base exception for storage operations"""
    pass


class FileNotFoundError(StorageError):
    """File not found in storage"""
    pass


class AccessDeniedError(StorageError):
    """Access denied to storage resource"""
    pass


class UnifiedStorage:
    """
    Unified storage interface using cloudpathlib
    
    Supports both local filesystem and cloud storage providers:
    - Local: file:///path/to/directory or /path/to/directory
    - AWS S3: s3://bucket-name/prefix
    - Google Cloud Storage: gs://bucket-name/prefix
    - Azure Blob Storage: az://container/prefix
    """
    
    def __init__(self, base_path: str):
        """Initialize with base path (local or cloud)"""
        # Handle different path formats
        if base_path.startswith('file://'):
            # Local file URI
            self.base_path = Path(base_path[7:])
        elif base_path.startswith(('s3://', 'gs://', 'az://')) and CLOUD_AVAILABLE:
            # Cloud storage URI
            self.base_path = CloudPath(base_path)
        else:
            # Assume local path
            self.base_path = Path(base_path)
        
        self.is_cloud = not isinstance(self.base_path, Path)
    
    async def ensure_room_structure(self, room_id: str) -> None:
        """Ensure room directory structure exists"""
        room_path = self.base_path / "rooms" / room_id
        logs_path = room_path / "logs"
        
        # Create directories if they don't exist
        if self.is_cloud:
            # For cloud storage, we don't need to create directories explicitly
            # They are created when we write files
            pass
        else:
            # For local storage, create directories
            room_path.mkdir(parents=True, exist_ok=True)
            logs_path.mkdir(parents=True, exist_ok=True)
        
        # Create metadata.json if it doesn't exist
        metadata_path = room_path / "metadata.json"
        if not await self.file_exists(metadata_path):
            metadata = {
                "room_id": room_id,
                "created_at": datetime.now().isoformat(),
                "version": "1.0",
                "protocol": "bucket-chat-v1"
            }
            await self.write_json(metadata_path, metadata)
    
    async def write_jsonl_file(self, file_path: Union[Path, CloudPath], events: List[str]) -> bool:
        """Write events to JSONL file"""
        try:
            content = "".join(events)
            
            if isinstance(file_path, Path):
                # Local file - ensure parent directory exists
                file_path.parent.mkdir(parents=True, exist_ok=True)
                
                if CLOUD_AVAILABLE:
                    async with aiofiles.open(file_path, 'w', encoding='utf-8') as f:
                        await f.write(content)
                else:
                    # Fallback to synchronous write
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write(content)
            else:
                # Cloud file
                if CLOUD_AVAILABLE:
                    file_path.write_text(content, encoding='utf-8')
                else:
                    raise StorageError("Cloud storage not available - install cloudpathlib")
            
            return True
        except Exception as e:
            print(f"Error writing JSONL file {file_path}: {e}")
            return False
    
    async def read_jsonl_file(self, file_path: Union[Path, CloudPath]) -> List[str]:
        """Read events from JSONL file"""
        try:
            if isinstance(file_path, Path):
                # Local file
                if CLOUD_AVAILABLE:
                    async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
                        content = await f.read()
                else:
                    # Fallback to synchronous read
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
            else:
                # Cloud file
                if CLOUD_AVAILABLE:
                    content = file_path.read_text(encoding='utf-8')
                else:
                    raise StorageError("Cloud storage not available - install cloudpathlib")
            
            return [line for line in content.split('\n') if line.strip()]
        except Exception as e:
            print(f"Error reading JSONL file {file_path}: {e}")
            return []
    
    async def list_log_files(self, room_id: str, date_filter: str = None) -> List[Union[Path, CloudPath]]:
        """List log files for a room, optionally filtered by date"""
        logs_path = self.base_path / "rooms" / room_id / "logs"
        
        try:
            if date_filter:
                # List files for specific date
                date_path = logs_path / date_filter
                if await self.file_exists(date_path):
                    if isinstance(date_path, Path):
                        return sorted(date_path.glob("messages_*.jsonl"))
                    else:
                        # For cloud storage, we need to list with prefix
                        files = []
                        try:
                            for item in date_path.iterdir():
                                if item.name.startswith("messages_") and item.name.endswith(".jsonl"):
                                    files.append(item)
                        except:
                            pass
                        return sorted(files)
            else:
                # Get all JSONL files recursively
                files = []
                if await self.file_exists(logs_path):
                    if isinstance(logs_path, Path):
                        # Local filesystem
                        for date_dir in logs_path.iterdir():
                            if date_dir.is_dir():
                                files.extend(date_dir.glob("messages_*.jsonl"))
                    else:
                        # Cloud storage
                        try:
                            for date_dir in logs_path.iterdir():
                                if date_dir.is_dir():
                                    for file in date_dir.iterdir():
                                        if file.name.startswith("messages_") and file.name.endswith(".jsonl"):
                                            files.append(file)
                        except:
                            pass
                
                return sorted(files)
        except Exception as e:
            print(f"Error listing log files: {e}")
        
        return []
    
    def get_daily_log_path(self, room_id: str, date_str: str, 
                          start_ts: int, end_ts: int, client_id: str) -> Union[Path, CloudPath]:
        """Get path for daily log file following protocol naming convention"""
        filename = f"messages_{start_ts}_{end_ts}_{client_id}.jsonl"
        return self.base_path / "rooms" / room_id / "logs" / date_str / filename
    
    async def write_json(self, file_path: Union[Path, CloudPath], data: dict) -> bool:
        """Write JSON data to file"""
        try:
            content = json.dumps(data, indent=2, ensure_ascii=False)
            
            if isinstance(file_path, Path):
                # Local file - ensure parent directory exists
                file_path.parent.mkdir(parents=True, exist_ok=True)
                
                if CLOUD_AVAILABLE:
                    async with aiofiles.open(file_path, 'w', encoding='utf-8') as f:
                        await f.write(content)
                else:
                    # Fallback to synchronous write
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write(content)
            else:
                # Cloud file
                if CLOUD_AVAILABLE:
                    file_path.write_text(content, encoding='utf-8')
                else:
                    raise StorageError("Cloud storage not available - install cloudpathlib")
            
            return True
        except Exception as e:
            print(f"Error writing JSON file {file_path}: {e}")
            return False
    
    async def read_json(self, file_path: Union[Path, CloudPath]) -> Optional[dict]:
        """Read JSON data from file"""
        try:
            if isinstance(file_path, Path):
                # Local file
                if not file_path.exists():
                    return None
                    
                if CLOUD_AVAILABLE:
                    async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
                        content = await f.read()
                else:
                    # Fallback to synchronous read
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
            else:
                # Cloud file
                if CLOUD_AVAILABLE:
                    if not file_path.exists():
                        return None
                    content = file_path.read_text(encoding='utf-8')
                else:
                    raise StorageError("Cloud storage not available - install cloudpathlib")
            
            return json.loads(content)
        except Exception as e:
            print(f"Error reading JSON file {file_path}: {e}")
            return None
    
    async def file_exists(self, file_path: Union[Path, CloudPath]) -> bool:
        """Check if file exists"""
        try:
            return file_path.exists()
        except Exception:
            return False
    
    async def delete_file(self, file_path: Union[Path, CloudPath]) -> bool:
        """Delete file (use with caution - violates immutability principle)"""
        try:
            if file_path.exists():
                file_path.unlink()
                return True
            return False
        except Exception as e:
            print(f"Error deleting file {file_path}: {e}")
            return False
    
    async def get_file_metadata(self, file_path: Union[Path, CloudPath]) -> Optional[dict]:
        """Get file metadata"""
        try:
            if not file_path.exists():
                return None
            
            if isinstance(file_path, Path):
                # Local file
                stat = file_path.stat()
                return {
                    'size': stat.st_size,
                    'modified': datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    'created': datetime.fromtimestamp(stat.st_ctime).isoformat(),
                    'path': str(file_path)
                }
            else:
                # Cloud file
                if CLOUD_AVAILABLE:
                    # Different cloud providers have different metadata formats
                    # This is a simplified version
                    return {
                        'path': str(file_path),
                        'exists': True
                    }
                else:
                    raise StorageError("Cloud storage not available - install cloudpathlib")
        except Exception as e:
            print(f"Error getting file metadata {file_path}: {e}")
            return None
    
    def get_room_metadata_path(self, room_id: str) -> Union[Path, CloudPath]:
        """Get path to room metadata file"""
        return self.base_path / "rooms" / room_id / "metadata.json"
    
    async def get_room_metadata(self, room_id: str) -> Optional[dict]:
        """Get room metadata"""
        metadata_path = self.get_room_metadata_path(room_id)
        return await self.read_json(metadata_path)
    
    async def update_room_metadata(self, room_id: str, metadata: dict) -> bool:
        """Update room metadata"""
        metadata_path = self.get_room_metadata_path(room_id)
        return await self.write_json(metadata_path, metadata)
    
    def get_storage_info(self) -> dict:
        """Get information about the storage backend"""
        return {
            'base_path': str(self.base_path),
            'is_cloud': self.is_cloud,
            'type': 'cloud' if self.is_cloud else 'local',
            'cloud_available': CLOUD_AVAILABLE
        }


# Utility functions
def parse_storage_uri(uri: str) -> dict:
    """Parse storage URI and return information about it"""
    if uri.startswith('s3://'):
        parts = uri[5:].split('/', 1)
        return {
            'type': 's3',
            'bucket': parts[0],
            'prefix': parts[1] if len(parts) > 1 else '',
            'uri': uri
        }
    elif uri.startswith('gs://'):
        parts = uri[5:].split('/', 1)
        return {
            'type': 'gcs',
            'bucket': parts[0],
            'prefix': parts[1] if len(parts) > 1 else '',
            'uri': uri
        }
    elif uri.startswith('az://'):
        parts = uri[5:].split('/', 1)
        return {
            'type': 'azure',
            'container': parts[0],
            'prefix': parts[1] if len(parts) > 1 else '',
            'uri': uri
        }
    elif uri.startswith('file://'):
        return {
            'type': 'local',
            'path': uri[7:],
            'uri': uri
        }
    else:
        # Assume local path
        return {
            'type': 'local',
            'path': uri,
            'uri': f'file://{uri}' if not uri.startswith('/') else f'file://{uri}'
        }


def get_date_string(timestamp_ms: int) -> str:
    """Get date string from timestamp for log file organization"""
    return date.fromtimestamp(timestamp_ms / 1000).isoformat()


def generate_client_id(user_id: str) -> str:
    """Generate a client ID from user ID for file naming"""
    # Remove domain part if email, keep alphanumeric chars
    if '@' in user_id:
        client_id = user_id.split('@')[0]
    else:
        client_id = user_id
    
    # Keep only alphanumeric characters and underscores
    return ''.join(c for c in client_id if c.isalnum() or c == '_')


if __name__ == "__main__":
    # Simple test
    async def test_storage():
        print("Testing Bucket Chat storage system...")
        
        # Test with local storage
        storage = UnifiedStorage('./test-storage')
        print(f"✅ Initialized storage: {storage.get_storage_info()}")
        
        # Test room structure creation
        await storage.ensure_room_structure('test_room')
        print("✅ Created room structure")
        
        # Test metadata
        metadata = await storage.get_room_metadata('test_room')
        print(f"✅ Room metadata: {metadata}")
        
        # Test file operations
        test_events = [
            '{"event_id": "test", "content": {"body": "Hello"}}\n',
            '{"event_id": "test2", "content": {"body": "World"}}\n'
        ]
        
        file_path = storage.get_daily_log_path(
            'test_room', 
            '2025-09-14', 
            1726315200000, 
            1726315300000, 
            'alice'
        )
        
        success = await storage.write_jsonl_file(file_path, test_events)
        if success:
            print("✅ Wrote JSONL file")
            
            # Read it back
            events = await storage.read_jsonl_file(file_path)
            print(f"✅ Read {len(events)} events")
        else:
            print("❌ Failed to write JSONL file")
        
        print("✅ Storage system test completed!")
    
    asyncio.run(test_storage())