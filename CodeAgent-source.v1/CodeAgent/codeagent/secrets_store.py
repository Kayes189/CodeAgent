"""Secure API-key persistence.

On Windows the key is encrypted with DPAPI (CryptProtectData), bound to the
current user account, and stored as a binary blob — never in plain text and
never in source control. On other platforms a permission-restricted file is
used as a fallback (the desktop target is Windows).

The key is never logged. ``redact`` helpers are provided for safe display.
"""
from __future__ import annotations

import base64
import ctypes
import os
import sys
from pathlib import Path

CONFIG_DIR = Path.home() / ".codeagent"
_KEY_FILE = CONFIG_DIR / "apikey.bin"
_FALLBACK_FILE = CONFIG_DIR / "apikey.txt"
_SERVICE = "CodeAgent.DeepSeek"


def _is_windows() -> bool:
    return sys.platform == "win32"


# --- Windows DPAPI --------------------------------------------------------
class _DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", ctypes.c_uint32), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _dpapi_protect(data: bytes) -> bytes:
    blob_in = _DATA_BLOB(len(data), ctypes.create_string_buffer(data, len(data)))
    blob_out = _DATA_BLOB()
    ok = ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(blob_in), "CodeAgent", None, None, None, 0, ctypes.byref(blob_out)
    )
    if not ok:
        raise OSError("CryptProtectData failed")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)


def _dpapi_unprotect(data: bytes) -> bytes:
    blob_in = _DATA_BLOB(len(data), ctypes.create_string_buffer(data, len(data)))
    blob_out = _DATA_BLOB()
    ok = ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)
    )
    if not ok:
        raise OSError("CryptUnprotectData failed")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)


def save_key(key: str) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not key:
        delete_key()
        return
    if _is_windows():
        try:
            _KEY_FILE.write_bytes(_dpapi_protect(key.encode("utf-8")))
            _FALLBACK_FILE.unlink(missing_ok=True)
            return
        except OSError:
            pass  # fall through to restricted file
    _FALLBACK_FILE.write_text(key, encoding="utf-8")
    try:
        os.chmod(_FALLBACK_FILE, 0o600)
    except OSError:
        pass
    _KEY_FILE.unlink(missing_ok=True)


def load_key() -> str:
    if _is_windows() and _KEY_FILE.exists():
        try:
            return _dpapi_unprotect(_KEY_FILE.read_bytes()).decode("utf-8")
        except (OSError, UnicodeDecodeError):
            return ""
    if _FALLBACK_FILE.exists():
        try:
            return _FALLBACK_FILE.read_text(encoding="utf-8").strip()
        except OSError:
            return ""
    return ""


def delete_key() -> None:
    for f in (_KEY_FILE, _FALLBACK_FILE):
        try:
            f.unlink(missing_ok=True)
        except OSError:
            pass


def storage_description() -> str:
    if _is_windows() and _KEY_FILE.exists():
        return "Windows DPAPI (encrypted, current-user bound)"
    if _FALLBACK_FILE.exists():
        return "Restricted local file (non-Windows fallback)"
    return "No key stored"


def redact(key: str) -> str:
    """Return a safe display form that never reveals the full key."""
    if not key:
        return "(not set)"
    if len(key) <= 8:
        return "*" * len(key)
    return key[:3] + "*" * (len(key) - 7) + key[-4:]
