"""Encrypted file vault for agent files: AES-256-GCM, key from the environment.

- Key: FILE_ENC_KEY (urlsafe-base64, 32 bytes). Never in code, never stored beside the data. FILE_ENC_KEY_PREV is optional
  and only decrypts, so a key can be rotated (re-save files to move them to the new key).
- Each file has a random 96-bit nonce. The authenticated data is "<file id>:<patient id>", so a blob copied to another
  file id or patient fails to decrypt.
- The on-disk name is a random storage key, fanned into folders; it says nothing about the person or the file.
- Fail closed: with no key the vault is unavailable and nothing is written in clear text.
"""
from __future__ import annotations

import base64
import os
import secrets
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

MAGIC = b"MT1"


class VaultError(Exception):
    pass


def _dir() -> Path:
    d = Path(os.getenv("VAULT_DIR") or Path(__file__).resolve().parents[1] / "vault")
    d.mkdir(parents=True, exist_ok=True)
    return d


def _key(var: str) -> bytes | None:
    raw = (os.getenv(var) or "").strip()
    if not raw:
        return None
    try:
        k = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
    except Exception:
        return None
    return k if len(k) == 32 else None


def available() -> bool:
    return _key("FILE_ENC_KEY") is not None


def new_storage_key() -> str:
    return secrets.token_hex(24)


def _path(storage_key: str) -> Path:
    if not storage_key.isalnum():
        raise VaultError("bad storage key")
    p = _dir() / storage_key[:2] / f"{storage_key}.bin"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _aad(file_id: str, patient_id: str) -> bytes:
    return f"{file_id}:{patient_id}".encode()


def put(storage_key: str, data: bytes, file_id: str, patient_id: str) -> None:
    key = _key("FILE_ENC_KEY")
    if key is None:
        raise VaultError("File storage is not configured.")
    nonce = os.urandom(12)
    blob = MAGIC + b"\x01" + nonce + AESGCM(key).encrypt(nonce, data, _aad(file_id, patient_id))
    tmp = _path(storage_key).with_suffix(".tmp")
    tmp.write_bytes(blob)
    os.chmod(tmp, 0o600)
    tmp.replace(_path(storage_key))


def get(storage_key: str, file_id: str, patient_id: str) -> bytes:
    p = _path(storage_key)
    if not p.exists():
        raise VaultError("File not found.")
    blob = p.read_bytes()
    if blob[:3] != MAGIC or len(blob) < 3 + 1 + 12 + 16:
        raise VaultError("Stored file is damaged.")
    key_id, nonce, ct = blob[3], blob[4:16], blob[16:]
    key = _key("FILE_ENC_KEY") if key_id == 1 else _key("FILE_ENC_KEY_PREV")
    if key is None:
        raise VaultError("File storage is not configured.")
    try:
        return AESGCM(key).decrypt(nonce, ct, _aad(file_id, patient_id))
    except InvalidTag:
        raise VaultError("Stored file failed its integrity check.")


def delete(storage_key: str) -> None:
    try:
        _path(storage_key).unlink(missing_ok=True)
    except OSError:
        pass
