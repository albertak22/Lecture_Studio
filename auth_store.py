"""Windows per-user DPAPI vault. Never falls back to plaintext."""
import ctypes
import json
import os
from pathlib import Path


def _crypt(data, decrypt=False):
    if os.name != 'nt':
        raise RuntimeError('로그인 정보 저장은 Windows에서 지원합니다. 현재 실행에서는 메모리만 사용하세요.')
    from ctypes import wintypes
    class Blob(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]
    buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    target = Blob()
    dll = ctypes.WinDLL('crypt32', use_last_error=True)
    fn = dll.CryptUnprotectData if decrypt else dll.CryptProtectData
    fn.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                   ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    fn.restype = wintypes.BOOL
    if not fn(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
        raise RuntimeError('Windows 암호화 저장소를 사용할 수 없습니다. 계정 정보를 다시 입력하세요.')
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    try:
        return ctypes.string_at(target.data, target.size)
    finally:
        kernel.LocalFree(target.data)


class CredentialStore:
    def __init__(self, directory):
        self.path = Path(directory) / 'credentials.dpapi'

    def load(self):
        if not self.path.exists():
            return {}
        try:
            result = json.loads(_crypt(self.path.read_bytes(), True))
            if not isinstance(result, dict):
                raise ValueError('invalid account')
            return result
        except Exception:
            raise RuntimeError('저장된 계정을 읽지 못했습니다. 이 PC에서 계정을 다시 등록하세요.') from None

    def save(self, credentials):
        encrypted = _crypt(json.dumps(credentials, ensure_ascii=False).encode('utf-8'))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix('.tmp')
        temp.write_bytes(encrypted)
        temp.replace(self.path)

    def clear(self):
        self.path.unlink(missing_ok=True)
        self.path.with_suffix('.tmp').unlink(missing_ok=True)
