from __future__ import annotations

import json
import base64
import hashlib
import hmac
import os
from pathlib import Path

SENSITIVE = {"authorization", "token", "access_token", "refresh_token", "password", "secret", "api_key", "apikey"}


def redact(value):
    if isinstance(value, dict):
        return {key: ("***" if key.lower() in SENSITIVE else redact(item)) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


class SecretStore:
    """Encrypt small local settings without a platform-specific native module.

    The previous implementation imported ``cryptography`` on every startup.
    Its current wheel crashes Python 3.14 on Windows before an exception can be
    handled.  This authenticated stream cipher uses only the standard library,
    keeping secrets encrypted at rest and making the desktop and CLI runtimes
    portable.  Existing Fernet values should be re-saved from the environment
    screen after upgrading.
    """

    def __init__(self, key_path: str | Path):
        self.key_path = Path(key_path)
        self.key_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.key_path.exists():
            self.key_path.write_bytes(base64.urlsafe_b64encode(os.urandom(32)))
        self._key = base64.urlsafe_b64decode(self.key_path.read_bytes().strip())

    def _keystream(self, nonce: bytes, size: int) -> bytes:
        blocks, counter = [], 0
        while sum(map(len, blocks)) < size:
            blocks.append(hashlib.sha256(self._key + nonce + counter.to_bytes(4, "big")).digest())
            counter += 1
        return b"".join(blocks)[:size]

    def encrypt_dict(self, values: dict) -> str:
        payload = json.dumps(values, ensure_ascii=False).encode("utf-8")
        nonce = os.urandom(16)
        encrypted = bytes(a ^ b for a, b in zip(payload, self._keystream(nonce, len(payload))))
        signature = hmac.new(self._key, nonce + encrypted, hashlib.sha256).digest()
        return "tp1:" + base64.urlsafe_b64encode(nonce + signature + encrypted).decode("ascii")

    def decrypt_dict(self, token: str) -> dict:
        if not token:
            return {}
        if not token.startswith("tp1:"):
            raise ValueError("旧版加密变量需要在桌面端重新保存")
        data = base64.urlsafe_b64decode(token[4:].encode("ascii"))
        nonce, signature, encrypted = data[:16], data[16:48], data[48:]
        expected = hmac.new(self._key, nonce + encrypted, hashlib.sha256).digest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError("密文校验失败")
        payload = bytes(a ^ b for a, b in zip(encrypted, self._keystream(nonce, len(encrypted))))
        return json.loads(payload.decode("utf-8"))


def split_sensitive(values: dict) -> tuple[dict, dict]:
    public, secrets = {}, {}
    for key, value in values.items():
        target = secrets if key.lower() in SENSITIVE or any(word in key.lower() for word in ("token", "password", "secret")) else public
        target[key] = value
    return public, secrets
