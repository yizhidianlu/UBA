"""User authentication service."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import os
from typing import Optional

from sqlalchemy.orm import Session

from ..database.models import User


@dataclass
class AuthResult:
    user: User


class AuthService:
    """Handle user registration and authentication."""

    def __init__(self, session: Session):
        self.session = session

    @staticmethod
    def _hash_password(password: str) -> str:
        salt = os.urandom(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 200000)
        return f"{salt.hex()}${digest.hex()}"

    @staticmethod
    def _verify_password(password: str, stored_hash: str) -> bool:
        try:
            salt_hex, digest_hex = stored_hash.split("$", 1)
        except ValueError:
            return False
        salt = bytes.fromhex(salt_hex)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 200000)
        return digest.hex() == digest_hex

    def register_user(self, email: str, password: str) -> AuthResult:
        normalized_email = email.strip().lower()
        existing = self.session.query(User).filter(User.email == normalized_email).first()
        if existing:
            raise ValueError("该邮箱已注册")

        password_hash = self._hash_password(password)
        user = User(email=normalized_email, password_hash=password_hash)
        self.session.add(user)
        self.session.commit()
        return AuthResult(user=user)

    def authenticate(self, email: str, password: str) -> Optional[AuthResult]:
        normalized_email = email.strip().lower()
        user = self.session.query(User).filter(User.email == normalized_email).first()
        if not user:
            return None
        if not self._verify_password(password, user.password_hash):
            return None
        user.last_login_at = datetime.now()
        self.session.commit()
        return AuthResult(user=user)
