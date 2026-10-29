"""Small COM client shared by integration tests and sequential benchmarks."""

import ctypes as C
from pathlib import Path
import uuid


class GUID(C.Structure):
    _fields_ = [('data', C.c_ubyte * 16)]

    def __init__(self, value):
        super().__init__((C.c_ubyte * 16).from_buffer_copy(uuid.UUID(value).bytes_le))


def method(pointer, index, result, *arguments):
    table = C.cast(pointer, C.POINTER(C.POINTER(C.c_void_p))).contents
    return C.WINFUNCTYPE(result, C.c_void_p, *arguments)(table[index])


def release(pointer):
    if pointer:
        method(pointer, 2, C.c_ulong)(pointer)


class Client:
    def __init__(self, package):
        self.dll = C.WinDLL(str(Path(package).resolve() / 'StepThumbnail.dll'))
        self.factory = C.c_void_p()
        self.thumb_iid = GUID('e357fccd-a995-4576-b01f-234630154e96')
        self.init_iid = GUID('b824b49d-22ac-4161-ac8a-9916e8fa3f7f')
        get_factory = self.dll.DllGetClassObject
        get_factory.argtypes = [C.POINTER(GUID), C.POINTER(GUID), C.POINTER(C.c_void_p)]
        get_factory.restype = C.c_long
        clsid = GUID('fad54c2d-a5a1-4d8e-9149-779862e2e961')
        iid = GUID('00000001-0000-0000-c000-000000000046')
        if get_factory(C.byref(clsid), C.byref(iid), C.byref(self.factory)) != 0:
            raise RuntimeError('Could not obtain provider factory')

    def close(self):
        release(self.factory)
        self.factory = C.c_void_p()

    def render(self, *, path=None, data=None, size=256):
        thumbnail, initialize, stream, bitmap = [C.c_void_p() for _ in range(4)]
        gdi = C.WinDLL('gdi32')
        gdi.DeleteObject.argtypes = [C.c_void_p]
        gdi.GetBitmapBits.argtypes = [C.c_void_p, C.c_long, C.c_void_p]
        try:
            create = method(self.factory, 3, C.c_long, C.c_void_p, C.POINTER(GUID), C.POINTER(C.c_void_p))
            if create(self.factory, None, C.byref(self.thumb_iid), C.byref(thumbnail)) != 0:
                raise RuntimeError('Could not create provider')
            query = method(thumbnail, 0, C.c_long, C.POINTER(GUID), C.POINTER(C.c_void_p))
            if query(thumbnail, C.byref(self.init_iid), C.byref(initialize)) != 0:
                raise RuntimeError('No stream initialization interface')
            shlwapi = C.WinDLL('shlwapi')
            if path is not None:
                open_stream = shlwapi.SHCreateStreamOnFileEx
                open_stream.argtypes = [C.c_wchar_p, C.c_uint32, C.c_uint32, C.c_int, C.c_void_p, C.POINTER(C.c_void_p)]
                open_stream.restype = C.c_long
                if open_stream(str(Path(path).resolve()), 0x20, 0, False, None, C.byref(stream)) != 0:
                    raise RuntimeError('Could not open model stream')
            else:
                open_stream = shlwapi.SHCreateMemStream
                open_stream.argtypes = [C.c_void_p, C.c_uint]
                open_stream.restype = C.c_void_p
                buffer = C.create_string_buffer(data)
                stream = C.c_void_p(open_stream(buffer, len(data)))
                if not stream:
                    raise RuntimeError('Could not create memory stream')
            init = method(initialize, 3, C.c_long, C.c_void_p, C.c_uint32)
            if init(initialize, stream, 0) != 0:
                raise RuntimeError('Could not initialize provider')
            get_thumb = method(thumbnail, 3, C.c_long, C.c_uint, C.POINTER(C.c_void_p), C.POINTER(C.c_int))
            alpha = C.c_int()
            hr = get_thumb(thumbnail, size, C.byref(bitmap), C.byref(alpha))
            if hr < 0:
                if bitmap:
                    raise RuntimeError('Failure returned a non-null bitmap')
                return hr, b''
            if not bitmap or alpha.value != 2:
                raise RuntimeError('Invalid successful thumbnail')
            pixels = C.create_string_buffer(size * size * 4)
            if gdi.GetBitmapBits(bitmap, len(pixels), pixels) != len(pixels):
                raise RuntimeError('Unexpected bitmap size')
            return hr, pixels.raw
        finally:
            if bitmap:
                gdi.DeleteObject(bitmap)
            for pointer in [stream, initialize, thumbnail]:
                release(pointer)
