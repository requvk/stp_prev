"""Run against the short-timeout test bridge and deterministic fake renderer."""

import concurrent.futures
import ctypes as C
import importlib.util
from pathlib import Path
import struct
import sys
import threading
import time
import unittest

PACKAGE = Path(sys.argv.pop(1)).resolve()
spec = importlib.util.spec_from_file_location('com_helpers', Path(__file__).with_name('com_helpers.py'))
helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helpers)


class WorkerLifecycleTests(unittest.TestCase):
    def setUp(self):
        time.sleep(0.8)
        self.dll = C.WinDLL(str(PACKAGE / 'StepThumbnail.dll'))
        self.assertEqual(self.dll.DllCanUnloadNow(), 0)
        self.client = helpers.Client(PACKAGE)

    def tearDown(self):
        self.client.close()

    def success(self, data=b'A'):
        hr, pixels = self.client.render(data=data, size=16)
        self.assertEqual(hr, 0)
        return struct.unpack_from('<I', pixels)[0]

    def test_reuse_error_and_request_limit(self):
        first = self.success()
        self.assertLess(self.client.render(data=b'E', size=16)[0], 0)
        self.assertEqual(self.success(), first)
        self.assertNotEqual(self.success(), first)  # Recycle after three test requests.

    def test_crash_bad_protocol_and_timeout_restart(self):
        for data in [b'X', b'B', b'S', b'H' + b'x' * (1024 * 1024)]:
            with self.subTest(action=data[:1]):
                first = self.success()
                started = time.monotonic()
                hr, pixels = self.client.render(data=data, size=16)
                self.assertLess(hr, 0)
                self.assertEqual(pixels, b'')
                self.assertLess(time.monotonic()-started, 3.0)
                self.assertNotEqual(self.success(), first)

    def test_concurrent_objects_do_not_mix_frames(self):
        def run(data):
            ole = C.OleDLL('ole32')
            ole.CoInitializeEx(None, 2)
            try:
                return self.success(data)
            finally:
                ole.CoUninitialize()

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(run, b'W'), executor.submit(run, b'W')]
            pids = [future.result(timeout=4) for future in futures]
        self.assertNotEqual(pids[0], pids[1])  # Two distinct isolated workers run concurrently.

    def test_idle_worker_allows_unloading(self):
        self.success()
        self.client.close()
        self.assertEqual(self.dll.DllCanUnloadNow(), 1)
        time.sleep(0.8)
        self.assertEqual(self.dll.DllCanUnloadNow(), 0)

    def test_queue_wait_consumes_request_deadline(self):
        def run():
            ole = C.OleDLL('ole32')
            ole.CoInitializeEx(None, 2)
            try:
                return self.client.render(data=b'L', size=16)[0]
            finally:
                ole.CoUninitialize()

        started = time.monotonic()
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(run) for _ in range(3)]
            results = [future.result(timeout=3) for future in futures]
        self.assertEqual(sum(result == 0 for result in results), 2)
        self.assertLess(time.monotonic()-started, 2.5)
        self.success()  # A timed out queued request cannot poison the next request.

    def test_same_object_rejects_overlapping_stream_reads(self):
        thumbnail, initialize = C.c_void_p(), C.c_void_p()
        stream = C.c_void_p()
        create = helpers.method(self.client.factory, 3, C.c_long, C.c_void_p,
                                C.POINTER(helpers.GUID), C.POINTER(C.c_void_p))
        self.assertEqual(create(self.client.factory, None, C.byref(self.client.thumb_iid), C.byref(thumbnail)), 0)
        try:
            query = helpers.method(thumbnail, 0, C.c_long, C.POINTER(helpers.GUID), C.POINTER(C.c_void_p))
            self.assertEqual(query(thumbnail, C.byref(self.client.init_iid), C.byref(initialize)), 0)
            open_stream = C.WinDLL('shlwapi').SHCreateMemStream
            open_stream.argtypes = [C.c_void_p, C.c_uint]
            open_stream.restype = C.c_void_p
            data = C.create_string_buffer(b'W')
            stream = C.c_void_p(open_stream(data, 1))
            init = helpers.method(initialize, 3, C.c_long, C.c_void_p, C.c_uint32)
            self.assertEqual(init(initialize, stream, 0), 0)
            barrier = threading.Barrier(2)

            def run():
                C.OleDLL('ole32').CoInitializeEx(None, 0)
                bitmap, alpha = C.c_void_p(), C.c_int()
                try:
                    get = helpers.method(thumbnail, 3, C.c_long, C.c_uint,
                                         C.POINTER(C.c_void_p), C.POINTER(C.c_int))
                    barrier.wait(timeout=2)
                    hr = get(thumbnail, 16, C.byref(bitmap), C.byref(alpha))
                    if hr < 0:
                        self.assertFalse(bitmap)
                    return hr
                finally:
                    if bitmap:
                        delete = C.WinDLL('gdi32').DeleteObject
                        delete.argtypes = [C.c_void_p]
                        delete(bitmap)
                    C.OleDLL('ole32').CoUninitialize()

            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                results = [future.result(timeout=3) for future in [executor.submit(run), executor.submit(run)]]
            self.assertEqual(sum(hr == 0 for hr in results), 1)
            self.assertIn(C.c_long(0x800700AA).value, results)  # ERROR_BUSY
        finally:
            for pointer in [stream, initialize, thumbnail]:
                helpers.release(pointer)


if __name__ == '__main__':
    C.OleDLL('ole32').CoInitializeEx(None, 2)
    unittest.main(verbosity=2)
