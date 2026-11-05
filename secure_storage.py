import ctypes
import sys
from ctypes import wintypes


if sys.platform == "win32":
    class _Credential(ctypes.Structure):
        _fields_ = [
            ("Flags", wintypes.DWORD),
            ("Type", wintypes.DWORD),
            ("TargetName", wintypes.LPWSTR),
            ("Comment", wintypes.LPWSTR),
            ("LastWritten", wintypes.FILETIME),
            ("CredentialBlobSize", wintypes.DWORD),
            ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
            ("Persist", wintypes.DWORD),
            ("AttributeCount", wintypes.DWORD),
            ("Attributes", ctypes.c_void_p),
            ("TargetAlias", wintypes.LPWSTR),
            ("UserName", wintypes.LPWSTR),
        ]

    _advapi32 = ctypes.WinDLL("Advapi32.dll", use_last_error=True)
    _advapi32.CredWriteW.argtypes = [
        ctypes.POINTER(_Credential),
        wintypes.DWORD,
    ]
    _advapi32.CredWriteW.restype = wintypes.BOOL
    _advapi32.CredReadW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(ctypes.POINTER(_Credential)),
    ]
    _advapi32.CredReadW.restype = wintypes.BOOL
    _advapi32.CredDeleteW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
    ]
    _advapi32.CredDeleteW.restype = wintypes.BOOL
    _advapi32.CredFree.argtypes = [ctypes.c_void_p]
    _advapi32.CredFree.restype = None


def _require_windows():
    if sys.platform != "win32":
        raise OSError("Secure credential storage requires Windows Credential Manager.")


def store_secret(target, secret, username=""):
    _require_windows()

    blob = str(secret).encode("utf-8")
    blob_buffer = (ctypes.c_ubyte * len(blob)).from_buffer_copy(blob)
    credential = _Credential(
        Flags=0,
        Type=1,
        TargetName=str(target),
        Comment=None,
        LastWritten=wintypes.FILETIME(),
        CredentialBlobSize=len(blob),
        CredentialBlob=ctypes.cast(
            blob_buffer,
            ctypes.POINTER(ctypes.c_ubyte),
        ),
        Persist=2,
        AttributeCount=0,
        Attributes=None,
        TargetAlias=None,
        UserName=str(username),
    )

    if not _advapi32.CredWriteW(ctypes.byref(credential), 0):
        raise ctypes.WinError(ctypes.get_last_error())


def read_secret(target):
    _require_windows()

    credential = ctypes.POINTER(_Credential)()
    if not _advapi32.CredReadW(
        str(target),
        1,
        0,
        ctypes.byref(credential),
    ):
        error_code = ctypes.get_last_error()
        if error_code == 1168:
            return None
        raise ctypes.WinError(error_code)

    try:
        value = ctypes.string_at(
            credential.contents.CredentialBlob,
            credential.contents.CredentialBlobSize,
        )
        return value.decode("utf-8")
    finally:
        _advapi32.CredFree(credential)


def delete_secret(target):
    _require_windows()

    if not _advapi32.CredDeleteW(str(target), 1, 0):
        error_code = ctypes.get_last_error()
        if error_code != 1168:
            raise ctypes.WinError(error_code)
