"""Ephemeral token vault: originals are AES-256-GCM encrypted under a random
per-session key that only ever lives in process memory."""
from __future__ import annotations

import os
import secrets

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


class Vault:
    def __init__(self) -> None:
        self._aes: AESGCM | None = AESGCM(AESGCM.generate_key(bit_length=256))
        self._items: dict[str, tuple[bytes, bytes]] = {}   # token -> (nonce, ciphertext)
        self._by_value: dict[tuple[str, str], str] = {}    # (type, original) -> token (dedupe)

    def put(self, kind: str, original: str) -> str:
        assert self._aes is not None, "vault closed"
        key = (kind, original)
        if key in self._by_value:
            return self._by_value[key]
        while True:
            token = f"⟦{kind}_{''.join(secrets.choice(_ALPHABET) for _ in range(5))}⟧"
            if token not in self._items:
                break
        nonce = os.urandom(12)
        self._items[token] = (nonce, self._aes.encrypt(nonce, original.encode(), token.encode()))
        self._by_value[key] = token
        return token

    def get(self, token: str) -> str | None:
        if self._aes is None or token not in self._items:
            return None
        nonce, ct = self._items[token]
        return self._aes.decrypt(nonce, ct, token.encode()).decode()

    def tokens(self) -> list[str]:
        return list(self._items)

    def originals(self) -> list[str]:
        return [v for t in self._items if (v := self.get(t))]

    def close(self) -> None:
        """Drop key + data (GDPR Art. 5 storage limitation)."""
        self._items.clear()
        self._by_value.clear()
        self._aes = None

    def __enter__(self) -> "Vault":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
