"""
Symmetric encryption helpers used to store Nutanix credentials at rest.

The Fernet key is derived deterministically from Django's ``SECRET_KEY`` so that
stored ciphertext can be decrypted across application restarts without requiring
an additional key to be managed by the operator.
"""

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


def _get_fernet():
    digest = hashlib.sha256(f'netbox-nutanix::{settings.SECRET_KEY}'.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt(value):
    """Encrypt a plaintext string. Returns an empty string for empty input."""
    if not value:
        return ''
    return _get_fernet().encrypt(value.encode()).decode()


def decrypt(value):
    """Decrypt a ciphertext string. Returns an empty string on failure."""
    if not value:
        return ''
    try:
        return _get_fernet().decrypt(value.encode()).decode()
    except (InvalidToken, ValueError):
        return ''
