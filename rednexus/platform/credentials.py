"""Operator-supplied credentials; never saved in the platform database or events."""
import json
import os
import base64
import ctypes
import tempfile
from pathlib import Path


def default_path():
    return Path.home() / ".rednexus" / "credentials.json"


def dpapi(data, decrypt=False):
    """Windows DPAPI binds persisted credentials to the current Windows user."""
    from ctypes import wintypes
    class Blob(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_byte))]
    buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
    target = Blob()
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    fn = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    fn.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                   ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    fn.restype = wintypes.BOOL
    if not fn(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
        raise OSError("Windows credential protection failed")
    try:
        return ctypes.string_at(target.data, target.size)
    finally:
        kernel.LocalFree(target.data)


def read_file(path):
    if path.stat().st_size > 65536:
        raise ValueError("credential file exceeds 64 KiB")
    if os.name != "nt" and path.stat().st_mode & 0o077:
        raise ValueError("credential file must be accessible only to its owner (chmod 600)")
    values = json.loads(path.read_text(encoding="utf-8-sig"))
    if "_dpapi" in values:
        if os.name != "nt":
            raise ValueError("Windows credentials must be opened by the original Windows user")
        values = json.loads(dpapi(base64.b64decode(values["_dpapi"]), decrypt=True))
    if not isinstance(values, dict):
        raise ValueError("invalid credential store")
    return values


def save_credential(name, value, path=None):
    path = Path(path or default_path()).expanduser()
    values = read_file(path) if path.exists() else {}
    values[name] = value.strip()
    data = json.dumps(values).encode()
    if os.name == "nt":
        data = json.dumps({"_dpapi": base64.b64encode(dpapi(data)).decode()}).encode()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(prefix="credential-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return path


def credential(settings, name):
    if not name:
        return None
    if value := os.getenv(name, "").strip():
        return value
    if settings.credential_file:
        path = Path(settings.credential_file).expanduser()
        if not path.exists():
            return None
        values = read_file(path)
        value = values.get(name)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None
