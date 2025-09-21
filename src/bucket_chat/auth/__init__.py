"""
Authentication module for Bucket Chat

This module provides OAuth 2.0 authentication support for various providers
including Google, Microsoft, and generic OAuth 2.0 services.
"""

# Note: OAuth implementation is optional and will be implemented later
# For now, we'll use a simple user ID based authentication

class SimpleAuth:
    """Simple authentication using user ID (for development/testing)"""
    
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.is_authenticated = bool(user_id)
    
    async def authenticate(self) -> bool:
        """Simple authentication - always succeeds if user_id is provided"""
        return self.is_authenticated
    
    def get_user_id(self) -> str:
        """Get the authenticated user ID"""
        return self.user_id

__all__ = ['SimpleAuth']