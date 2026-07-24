import html
from datetime import datetime, timedelta, timezone
from typing import Any, Union, Optional
from jose import jwt, JWTError
from passlib.context import CryptContext
from app.core.config import settings

def sanitize_string(input_text: str) -> str:
    """Sanitize input strings by escaping HTML and dangerous injection tags."""
    if not input_text:
        return ""
    return html.escape(input_text.strip())

# Passlib Crypt Context for password hashing
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain text password against its pbkdf2_sha256 hash."""
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """Generate a pbkdf2_sha256 hash of the plain text password."""
    return pwd_context.hash(password)

def create_access_token(
    subject: Union[str, Any],
    expires_delta: Optional[timedelta] = None
) -> str:
    """Generate a short-lived JWT Access Token."""
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode = {
        "exp": expire,
        "sub": str(subject),
        "type": "access"
    }
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

def create_refresh_token(
    subject: Union[str, Any],
    expires_delta: Optional[timedelta] = None
) -> str:
    """Generate a long-lived JWT Refresh Token."""
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        
    to_encode = {
        "exp": expire,
        "sub": str(subject),
        "type": "refresh"
    }
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

def decode_token(token: str) -> Optional[dict]:
    """Decode and verify a JWT token returning its payload or None if invalid."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except JWTError:
        return None


import base64
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes

def _get_fernet_cipher() -> Fernet:
    """Derive a URL-safe 32-byte Fernet key from settings.SECRET_KEY."""
    digest = hashlib.sha256(settings.SECRET_KEY.encode('utf-8')).digest()
    key_b64 = base64.urlsafe_b64encode(digest)
    return Fernet(key_b64)

import hashlib

def encrypt_token(plain_token: str) -> str:
    """Encrypt OAuth access or refresh token before database storage using AES-256 Fernet."""
    if not plain_token:
        return ""
    cipher = _get_fernet_cipher()
    return cipher.encrypt(plain_token.encode('utf-8')).decode('utf-8')

def decrypt_token(encrypted_token: str) -> str:
    """Decrypt stored OAuth access or refresh token at runtime for outbound requests."""
    if not encrypted_token:
        return ""
    cipher = _get_fernet_cipher()
    return cipher.decrypt(encrypted_token.encode('utf-8')).decode('utf-8')

