import ctypes
from ctypes import wintypes

ERROR_ALREADY_EXISTS = 183


class NamedMutex:
    def __init__(self, handle: int, kernel32):
        self._handle = handle
        self._kernel32 = kernel32

    def close(self) -> None:
        if self._handle:
            self._kernel32.CloseHandle(self._handle)
            self._handle = 0


def claim_named_mutex(name: str) -> NamedMutex | None:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel32.CreateMutexW(None, False, name)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    mutex = NamedMutex(handle, kernel32)
    if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        mutex.close()
        return None
    return mutex
