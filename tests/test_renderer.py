"""Run with packaged Python: runtime/python.exe tests/test_renderer.py PACKAGE."""

import ctypes as C
from ctypes import wintypes as W
import importlib.util
import io
from pathlib import Path
import struct
import subprocess
import sys
import time
import unittest
import uuid

PACKAGE = Path(sys.argv.pop(1)).resolve()
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("render_step", PACKAGE / "render_step.py")
renderer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(renderer)
FIXTURES = ROOT / "artifacts" / "test-models"
FIXTURES.mkdir(parents=True, exist_ok=True)


def generate_models():
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
    from OCP.BRep import BRep_Builder
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt, gp_Trsf, gp_Vec
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer
    from OCP.TopoDS import TopoDS_Compound

    box = BRepPrimAPI_MakeBox(40, 30, 12).Shape()
    hole = BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(20, 15, -1), gp_Dir(0, 0, 1)), 7, 14).Shape()
    bracket = BRepAlgoAPI_Cut(box, hole).Shape()
    cylinder = BRepPrimAPI_MakeCylinder(10, 30).Shape()
    move = gp_Trsf()
    move.SetTranslation(gp_Vec(65, 0, 0))
    assembly = TopoDS_Compound()
    builder = BRep_Builder()
    builder.MakeCompound(assembly)
    builder.Add(assembly, bracket)
    builder.Add(assembly, BRepBuilderAPI_Transform(cylinder, move, False).Shape())
    for name, shape in [("bracket.step", bracket), ("cylinder.stp", cylinder), ("assembly.step", assembly)]:
        writer = STEPControl_Writer()
        writer.Transfer(shape, STEPControl_AsIs)
        if writer.Write(str(FIXTURES / name)) != IFSelect_RetDone:
            raise RuntimeError("Could not generate fixture")


class RendererTests(unittest.TestCase):
    def test_native_raster_matches_reference(self):
        import numpy as np

        reference_spec = importlib.util.spec_from_file_location('raster_reference', ROOT / 'tests' / 'raster_reference.py')
        reference = importlib.util.module_from_spec(reference_spec)
        reference_spec.loader.exec_module(reference)
        triangles = renderer.tessellate(renderer.read_shape((FIXTURES / 'assembly.step').read_bytes()))
        for size in [48, 96, 256, 512]:
            with self.subTest(size=size):
                expected = np.array(reference.rasterize(triangles, size))
                actual = np.array(renderer.rasterize(triangles, size))
                difference = np.abs(expected.astype(np.int16) - actual.astype(np.int16))
                self.assertLess(float(difference.mean()), 0.05)
                self.assertLess(float(np.any(difference > 2, axis=2).mean()), 0.001)

    def test_geometry_and_sizes(self):
        import numpy as np

        for name in ["bracket.step", "cylinder.stp", "assembly.step"]:
            file = FIXTURES / name
            for size in [48, 96, 256, 512]:
                with self.subTest(file=file.name, size=size):
                    image = renderer.render(file.read_bytes(), size)
                    pixels = np.array(image)
                    self.assertEqual(image.size, (size, size))
                    self.assertGreater((pixels[:, :, 3] > 0).sum(), size * size * 0.04)
                    self.assertEqual(int(pixels[0, 0, 3]), 0)
                    image.save(FIXTURES / f"{file.stem}-{size}.png")

    def test_invalid_inputs(self):
        for data, size in [(b"", 256), (b"broken model", 256), (b"ISO-10303-21;END-ISO-10303-21;", 256), (b"x", 0), (b"x", 1025)]:
            with self.subTest(data=data, size=size), self.assertRaises(ValueError):
                renderer.render(data, size)

    def test_assembly_location(self):
        triangles = renderer.tessellate(renderer.read_shape((FIXTURES / "assembly.step").read_bytes()))
        self.assertGreater(float(triangles[:, :, 0].max()), 74)

    def test_binary_protocol(self):
        from PIL import Image

        size = 96
        completed = subprocess.run(
            [str(PACKAGE / "runtime" / "python.exe"), "-I", "-B", str(PACKAGE / "render_step.py"), "--pipe", str(size)],
            input=(FIXTURES / "bracket.step").read_bytes(), capture_output=True, timeout=20,
            creationflags=0x08000000,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr.decode(errors="replace"))
        self.assertEqual(struct.unpack("<4sII", completed.stdout[:12]), (b"STP1", size, size))
        self.assertEqual(len(completed.stdout), 12 + size * size * 4)
        image = Image.frombytes("RGBA", (size, size), completed.stdout[12:], "raw", "BGRA")
        for r, g, b, alpha in image.get_flattened_data():
            self.assertLessEqual(max(r, g, b), alpha)

    def test_server_multiple_requests_and_model_error(self):
        model = (FIXTURES / 'bracket.step').read_bytes()
        inputs = [(48, model), (96, b'broken model'), (256, model)]
        requests = b''.join(struct.pack('<4sII', b'REQ2', size, len(data)) + data for size, data in inputs)
        process = subprocess.run(
            [str(PACKAGE / 'runtime' / 'python.exe'), '-I', '-B', str(PACKAGE / 'render_step.py'), '--server'],
            input=requests, capture_output=True, timeout=20, creationflags=0x08000000,
        )
        self.assertEqual(process.returncode, 0, process.stderr.decode(errors='replace'))
        offset = 0
        for size, data in inputs:
            header = struct.unpack_from('<4sIII', process.stdout, offset)
            offset += 16
            self.assertEqual(header[0], b'STP2')
            if data == b'broken model':
                self.assertEqual(header[1:], (1, 0, 0))
            else:
                self.assertEqual(header[1:], (0, size, size))
                expected = renderer.encode_bgra(renderer.render(data, size))
                self.assertEqual(process.stdout[offset:offset+len(expected)], expected)
                offset += len(expected)
        self.assertEqual(offset, len(process.stdout))

    def test_server_rejects_oversized_frame(self):
        process = subprocess.run(
            [str(PACKAGE / 'runtime' / 'python.exe'), '-I', '-B', str(PACKAGE / 'render_step.py'), '--server'],
            input=struct.pack('<4sII', b'REQ2', 256, renderer.MAX_INPUT+1),
            capture_output=True, timeout=5, creationflags=0x08000000,
        )
        self.assertNotEqual(process.returncode, 0)
        self.assertEqual(process.stdout, b'')

    def test_server_exits_when_idle_without_parent_closing_pipe(self):
        process = subprocess.Popen(
            [str(PACKAGE / 'runtime' / 'python.exe'), '-I', '-B', str(PACKAGE / 'render_step.py'),
             '--server', '--idle-ms', '200'],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=0x08000000,
        )
        try:
            data = b'broken model'
            process.stdin.write(struct.pack('<4sII', b'REQ2', 96, len(data)) + data)
            process.stdin.flush()
            self.assertEqual(process.wait(timeout=3), 0)
            self.assertEqual(process.stdout.read(), struct.pack('<4sIII', b'STP2', 1, 0, 0))
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=3)
            for stream in [process.stdin, process.stdout, process.stderr]:
                stream.close()


class GUID(C.Structure):
    _fields_ = [("data", C.c_ubyte * 16)]

    def __init__(self, value):
        super().__init__((C.c_ubyte * 16).from_buffer_copy(uuid.UUID(value).bytes_le))


def method(pointer, index, result, *arguments):
    table = C.cast(pointer, C.POINTER(C.POINTER(C.c_void_p))).contents
    return C.WINFUNCTYPE(result, C.c_void_p, *arguments)(table[index])


class NativeTests(unittest.TestCase):
    def test_com_contract_and_bitmap(self):
        from PIL import Image

        dll = C.WinDLL(str(PACKAGE / "StepThumbnail.dll"))
        unload = dll.DllCanUnloadNow
        unload.restype = C.c_long
        self.assertEqual(unload(), 0)
        get_factory = dll.DllGetClassObject
        get_factory.argtypes = [C.POINTER(GUID), C.POINTER(GUID), C.POINTER(C.c_void_p)]
        get_factory.restype = C.c_long
        factory = C.c_void_p()
        clsid = GUID("fad54c2d-a5a1-4d8e-9149-779862e2e961")
        iid_factory = GUID("00000001-0000-0000-c000-000000000046")
        iid_thumbnail = GUID("e357fccd-a995-4576-b01f-234630154e96")
        iid_initialize = GUID("b824b49d-22ac-4161-ac8a-9916e8fa3f7f")
        self.assertEqual(get_factory(C.byref(clsid), C.byref(iid_factory), C.byref(factory)), 0)
        self.assertEqual(unload(), 1)
        thumbnail = C.c_void_p()
        create = method(factory, 3, C.c_long, C.c_void_p, C.POINTER(GUID), C.POINTER(C.c_void_p))
        self.assertEqual(create(factory, None, C.byref(iid_thumbnail), C.byref(thumbnail)), 0)
        get_thumb = method(thumbnail, 3, C.c_long, C.c_uint, C.POINTER(C.c_void_p), C.POINTER(C.c_int))
        bitmap, alpha = C.c_void_p(), C.c_int()
        self.assertLess(get_thumb(thumbnail, 96, C.byref(bitmap), C.byref(alpha)), 0)
        initialize = C.c_void_p()
        query = method(thumbnail, 0, C.c_long, C.POINTER(GUID), C.POINTER(C.c_void_p))
        self.assertEqual(query(thumbnail, C.byref(iid_initialize), C.byref(initialize)), 0)
        shell = C.WinDLL("shlwapi")
        stream_file = shell.SHCreateStreamOnFileEx
        stream_file.argtypes = [W.LPCWSTR, W.DWORD, W.DWORD, W.BOOL, C.c_void_p, C.POINTER(C.c_void_p)]
        stream_file.restype = C.c_long
        stream = C.c_void_p()
        self.assertEqual(stream_file(str(FIXTURES / "bracket.step"), 0x20, 0, False, None, C.byref(stream)), 0)
        init = method(initialize, 3, C.c_long, C.c_void_p, W.DWORD)
        self.assertEqual(init(initialize, stream, 0), 0)
        self.assertLess(init(initialize, stream, 0), 0)
        self.assertLess(get_thumb(thumbnail, 0, C.byref(bitmap), C.byref(alpha)), 0)
        self.assertLess(get_thumb(thumbnail, 1025, C.byref(bitmap), C.byref(alpha)), 0)
        gdi = C.WinDLL("gdi32")
        gdi.GetBitmapBits.argtypes = [C.c_void_p, C.c_long, C.c_void_p]
        gdi.DeleteObject.argtypes = [C.c_void_p]
        for size in [48, 96, 256, 512]:
            started = time.monotonic()
            self.assertEqual(get_thumb(thumbnail, size, C.byref(bitmap), C.byref(alpha)), 0)
            self.assertEqual(alpha.value, 2)  # WTSAT_ARGB
            pixels = C.create_string_buffer(size * size * 4)
            self.assertEqual(gdi.GetBitmapBits(bitmap, len(pixels), pixels), len(pixels))
            Image.frombytes("RGBA", (size, size), pixels.raw, "raw", "BGRA").save(FIXTURES / f"native-{size}.png")
            self.assertTrue(gdi.DeleteObject(bitmap))
            print(f"Native COM {size}px: {time.monotonic() - started:.2f}s", flush=True)
        for pointer in [stream, initialize, thumbnail, factory]:
            method(pointer, 2, C.c_ulong)(pointer)
        self.assertEqual(unload(), 1)  # Idle worker temporarily keeps the DLL loaded.

        for file in (ROOT / 'artifacts' / 'self-contained').glob('Chain-*.step'):
            with self.subTest(real_assembly=file.name):
                self.assertEqual(get_factory(C.byref(clsid), C.byref(iid_factory), C.byref(factory)), 0)
                self.assertEqual(create(factory, None, C.byref(iid_thumbnail), C.byref(thumbnail)), 0)
                self.assertEqual(query(thumbnail, C.byref(iid_initialize), C.byref(initialize)), 0)
                self.assertEqual(stream_file(str(file), 0x20, 0, False, None, C.byref(stream)), 0)
                self.assertEqual(init(initialize, stream, 0), 0)
                started = time.monotonic()
                self.assertEqual(get_thumb(thumbnail, 256, C.byref(bitmap), C.byref(alpha)), 0)
                print(f'Native real assembly {file.name}: {time.monotonic()-started:.3f}s', flush=True)
                self.assertEqual(alpha.value, 2)
                pixels = C.create_string_buffer(256 * 256 * 4)
                self.assertEqual(gdi.GetBitmapBits(bitmap, len(pixels), pixels), len(pixels))
                self.assertTrue(any(pixels.raw[3::4]))
                self.assertTrue(gdi.DeleteObject(bitmap))
                for pointer in [stream, initialize, thumbnail, factory]:
                    method(pointer, 2, C.c_ulong)(pointer)
                self.assertEqual(unload(), 1)

        # Exercise errors through the actual DLL/worker, including early size rejection.
        empty = FIXTURES / 'empty.step'
        empty.write_bytes(b'')
        broken = FIXTURES / 'broken.step'
        broken.write_bytes(b'not a STEP model')
        oversized = FIXTURES / 'oversized.step'
        with oversized.open('wb') as output:
            output.truncate(renderer.MAX_INPUT + 1)
        try:
            for file in [empty, broken, oversized]:
                with self.subTest(file=file.name):
                    self.assertEqual(get_factory(C.byref(clsid), C.byref(iid_factory), C.byref(factory)), 0)
                    self.assertEqual(create(factory, None, C.byref(iid_thumbnail), C.byref(thumbnail)), 0)
                    self.assertEqual(query(thumbnail, C.byref(iid_initialize), C.byref(initialize)), 0)
                    self.assertEqual(stream_file(str(file), 0x20, 0, False, None, C.byref(stream)), 0)
                    self.assertEqual(init(initialize, stream, 0), 0)
                    bitmap.value = 0x1234
                    self.assertLess(get_thumb(thumbnail, 96, C.byref(bitmap), C.byref(alpha)), 0)
                    self.assertIsNone(bitmap.value)
                    for pointer in [stream, initialize, thumbnail, factory]:
                        method(pointer, 2, C.c_ulong)(pointer)
                    self.assertEqual(unload(), 1)
        finally:
            oversized.unlink()

    def test_idle_worker_releases_host(self):
        dll = C.WinDLL(str(PACKAGE / 'StepThumbnail.dll'))
        time.sleep(30.5)
        self.assertEqual(dll.DllCanUnloadNow(), 0)


if __name__ == "__main__":
    C.OleDLL("ole32").CoInitializeEx(None, 2)
    generate_models()
    unittest.main(verbosity=2)
