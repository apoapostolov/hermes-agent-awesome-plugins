"""Optional Windows DPAPI protection for plugin-owned credential files."""
import base64
import os
from pathlib import Path
from cryptography.fernet import Fernet

FIELDS = {"client_secret", "refresh_token", "access_token"}


def _crypt(value, decrypt=False):
    if os.name != "nt":
        raise RuntimeError("Windows DPAPI protection is available only on Windows")
    import ctypes
    from ctypes import wintypes
    class Blob(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]
    buf = ctypes.create_string_buffer(value)
    source = Blob(len(value), ctypes.cast(buf, ctypes.POINTER(ctypes.c_ubyte)))
    result = Blob()
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    operation = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    if not operation(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(result)):
        raise RuntimeError("Windows could not unlock the Reddit credential file for this user")
    try:
        return ctypes.string_at(result.data, result.size)
    finally:
        kernel.LocalFree(result.data)


def _cipher(home=None, rotate=False):
    """Return the profile cipher.

    ``rotate`` is for the write path only. Reading must never replace the key:
    an unreadable key is reported, and the credentials stay recoverable by
    saving replacements, which re-encrypts through ``rotate=True``.
    """
    from . import client, coordination
    root = Path(home or client.hermes_home()) / "plugin-data/reddit"
    path = root / "storage-key.json"
    with coordination.file_lock(root / "storage-key.lock"):
        if path.exists():
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                raise RuntimeError("Reddit storage key is unreadable right now; retry shortly") from None
            try:
                record = __import__("json").loads(text)
                key = _crypt(base64.b64decode(record["dpapi"]), True) if "dpapi" in record else record["private_file"].encode("ascii")
                return Fernet(key)
            except (ValueError, KeyError, TypeError, RuntimeError):
                if not rotate:
                    raise RuntimeError(
                        "Reddit storage key cannot be unlocked; save replacement credentials to recover"
                    ) from None
                import logging
                logging.getLogger(__name__).warning("Reddit storage key could not be unlocked; rotating it for a rewrite")
        key = Fernet.generate_key()
        if os.name == "nt":
            record = {"dpapi": base64.b64encode(_crypt(key)).decode("ascii")}
        else:
            record = {"private_file": key.decode("ascii")}
        client._atomic_write(path, __import__("json").dumps(record))
    return Fernet(key)


def encode(record, enabled=False, home=None):
    result = dict(record)
    cipher = _cipher(home, rotate=True)
    for key in FIELDS:
        value = result.get(key)
        if isinstance(value, str) and value:
            result[key] = {"$fernet": cipher.encrypt(value.encode()).decode("ascii")}
    return result


def decode(record, home=None):
    result = dict(record) if isinstance(record, dict) else {}
    for key in FIELDS:
        value = result.get(key)
        if isinstance(value, dict) and "$dpapi" in value:
            result[key] = _crypt(base64.b64decode(value["$dpapi"], validate=True), True).decode()
        elif isinstance(value, dict) and "$fernet" in value:
            try:
                result[key] = _cipher(home).decrypt(value["$fernet"].encode("ascii")).decode()
            except Exception:
                raise RuntimeError("Reddit credential decryption failed; restore its storage key or sign in again") from None
    return result
