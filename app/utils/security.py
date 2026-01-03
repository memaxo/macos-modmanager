"""Security utilities for encrypting sensitive data"""
from cryptography.fernet import Fernet
from pathlib import Path
import base64
import os
from app.config import settings


class EncryptionError(Exception):
    """Exception raised during encryption/decryption operations"""
    pass


class SecureStorage:
    """Handles encryption and decryption of sensitive data"""
    
    def __init__(self):
        self._key = None
        self._cipher = None
        self._key_file = settings.base_data_dir / ".encryption_key"
        self._load_or_create_key()
    
    def _load_or_create_key(self):
        """Load encryption key from file or create a new one"""
        if self._key_file.exists():
            try:
                with open(self._key_file, 'rb') as f:
                    self._key = f.read()
            except Exception as e:
                raise EncryptionError(f"Failed to load encryption key: {e}")
        else:
            # Generate a new key
            self._key = Fernet.generate_key()
            try:
                # Ensure directory exists
                self._key_file.parent.mkdir(parents=True, exist_ok=True)
                # Set restrictive permissions (owner read/write only)
                with open(self._key_file, 'wb') as f:
                    f.write(self._key)
                os.chmod(self._key_file, 0o600)  # rw-------
            except Exception as e:
                raise EncryptionError(f"Failed to save encryption key: {e}")
        
        try:
            self._cipher = Fernet(self._key)
        except Exception as e:
            raise EncryptionError(f"Failed to initialize cipher: {e}")
    
    def encrypt(self, plaintext: str) -> str:
        """Encrypt a plaintext string"""
        if not plaintext:
            return ""
        
        if not self._cipher:
            raise EncryptionError("Cipher not initialized")
        
        try:
            encrypted_bytes = self._cipher.encrypt(plaintext.encode('utf-8'))
            # Return base64 encoded string for safe storage in database
            return base64.b64encode(encrypted_bytes).decode('utf-8')
        except Exception as e:
            raise EncryptionError(f"Encryption failed: {e}")
    
    def decrypt(self, ciphertext: str) -> str:
        """Decrypt a ciphertext string"""
        if not ciphertext:
            return ""
        
        if not self._cipher:
            raise EncryptionError("Cipher not initialized")
        
        try:
            # Decode from base64 first
            encrypted_bytes = base64.b64decode(ciphertext.encode('utf-8'))
            decrypted_bytes = self._cipher.decrypt(encrypted_bytes)
            return decrypted_bytes.decode('utf-8')
        except Exception as e:
            raise EncryptionError(f"Decryption failed: {e}")
    
    def is_encrypted(self, value: str) -> bool:
        """Check if a value appears to be encrypted"""
        if not value:
            return False
        
        try:
            # Try to decode as base64
            decoded = base64.b64decode(value.encode('utf-8'), validate=True)
            # Fernet tokens are at least 57 bytes (version + timestamp + IV + HMAC + min ciphertext)
            # But we'll be more lenient - if it's valid base64 and reasonably long, check structure
            if len(decoded) < 57:
                return False
            
            # Fernet tokens start with version byte 0x80
            # Try to decrypt to verify (but don't raise exception)
            try:
                self._cipher.decrypt(decoded, ttl=None)  # ttl=None means no expiration check
                return True
            except Exception:
                # Decryption failed, so it's not encrypted with our key
                # But it might still be encrypted with a different key
                # Check if it has the Fernet structure (starts with 0x80)
                return decoded[0] == 0x80
        except Exception:
            # If base64 decode fails, it's not encrypted
            return False


# Global instance
_secure_storage = None


def get_secure_storage() -> SecureStorage:
    """Get or create the global secure storage instance"""
    global _secure_storage
    if _secure_storage is None:
        _secure_storage = SecureStorage()
    return _secure_storage


def encrypt_value(value: str) -> str:
    """Encrypt a value using the secure storage"""
    return get_secure_storage().encrypt(value)


def decrypt_value(value: str) -> str:
    """Decrypt a value using the secure storage"""
    return get_secure_storage().decrypt(value)


def is_encrypted(value: str) -> bool:
    """Check if a value is encrypted"""
    return get_secure_storage().is_encrypted(value)
