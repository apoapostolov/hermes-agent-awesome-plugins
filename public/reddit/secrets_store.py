"""Optional Windows DPAPI protection for plugin-owned credential files."""
import base64
import os

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


def encode(record, enabled=False):
    result = dict(record)
    if enabled:
        for key in FIELDS:
            value = result.get(key)
            if isinstance(value, str) and value:
                result[key] = {"$dpapi": base64.b64encode(_crypt(value.encode())).decode("ascii")}
    return result


def decode(record):
    result = dict(record) if isinstance(record, dict) else {}
    for key in FIELDS:
        value = result.get(key)
        if isinstance(value, dict) and "$dpapi" in value:
            result[key] = _crypt(base64.b64decode(value["$dpapi"], validate=True), True).decode()
    return result
