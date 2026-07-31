from __future__ import annotations

import json
from pathlib import Path

SENSITIVE = {"authorization", "token", "access_token", "refresh_token", "password", "secret", "api_key", "apikey"}


def redact(value):
    if isinstance(value, dict):
        return {key: ("***" if key.lower() in SENSITIVE else redact(item)) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


class SecretStore:
    """Encrypt small local settings with a per-installation Fernet key."""

    def __init__(self, key_path: str | Path):
        from cryptography.fernet import Fernet

        self.key_path = Path(key_path)
        self.key_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.key_path.exists():
            self.key_path.write_bytes(Fernet.generate_key())
        self._cipher = Fernet(self.key_path.read_bytes().strip())

    def encrypt_dict(self, values: dict) -> str:
        payload = json.dumps(values, ensure_ascii=False).encode("utf-8")
        return self._cipher.encrypt(payload).decode("ascii")

    def decrypt_dict(self, token: str) -> dict:
        if not token:
            return {}
        return json.loads(self._cipher.decrypt(token.encode("ascii")).decode("utf-8"))


def split_sensitive(values: dict) -> tuple[dict, dict]:
    public, secrets = {}, {}
    for key, value in values.items():
        target = secrets if key.lower() in SENSITIVE or any(word in key.lower() for word in ("token", "password", "secret")) else public
        target[key] = value
    return public, secrets
