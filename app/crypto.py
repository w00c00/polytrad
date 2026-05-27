import os
import base64
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from app.config import get_settings


def _derive_key(master: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=600_000)
    return base64.urlsafe_b64encode(kdf.derive(master.encode()))


def encrypt_secret(plaintext: str) -> str:
    """加密字符串，返回 salt_hex:ciphertext 格式"""
    salt = os.urandom(16)
    key = _derive_key(get_settings().polytrad_master_key, salt)
    f = Fernet(key)
    ct = f.encrypt(plaintext.encode()).decode()
    return f"{salt.hex()}:{ct}"


def decrypt_secret(token: str) -> str:
    """解密 salt_hex:ciphertext 格式的字符串"""
    salt_hex, ct = token.split(":", 1)
    salt = bytes.fromhex(salt_hex)
    key = _derive_key(get_settings().polytrad_master_key, salt)
    f = Fernet(key)
    return f.decrypt(ct.encode()).decode()
