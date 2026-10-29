"""Headless STEP -> RGBA renderer. No user files, network, or GPU access."""

import argparse
import io
import math
import os
from pathlib import Path
import struct
import sys
import time

MAX_INPUT = 64 * 1024 * 1024
MAX_TRIANGLES = 200_000


def read_shape(data):
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.STEPControl import STEPControl_Reader

    reader = STEPControl_Reader()
    status = reader.ReadStream("thumbnail.step", io.BytesIO(data))
    if status != IFSelect_RetDone:
        raise ValueError('Could not parse STEP')
    if reader.TransferRoots() == 0:
        if b'DOCUMENT_FILE' in data.upper():
            raise ValueError('Assembly uses external STEP documents; a self-contained STEP export is required')
        raise ValueError("STEP contains no transferable geometry")
    shape = reader.OneShape()
    if shape.IsNull():
        raise ValueError("Empty STEP shape")
    return shape


def tessellate(shape):
    import numpy as np
    from OCP.Bnd import Bnd_Box
    from OCP.BRep import BRep_Tool
    from OCP.BRepBndLib import BRepBndLib
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.TopAbs import TopAbs_FACE, TopAbs_REVERSED
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopoDS import TopoDS

    bounds = Bnd_Box()
    BRepBndLib.Add_s(shape, bounds)
    if bounds.IsVoid() or bounds.IsOpen():
        raise ValueError("Unbounded or empty geometry")
    box = bounds.Get()
    diagonal = math.dist(box[:3], box[3:])
    if not math.isfinite(diagonal) or diagonal <= 1e-12:
        raise ValueError("Degenerate model bounds")
    BRepMesh_IncrementalMesh(shape, max(diagonal * 0.002, 1e-7), False, 0.35, False)
    triangles = []
    count = 0
    explorer = TopExp_Explorer(shape, TopAbs_FACE)
    while explorer.More():
        face = TopoDS.Face_s(explorer.Current())
        location = TopLoc_Location()
        mesh = BRep_Tool.Triangulation_s(face, location)
        if mesh is not None:
            count += mesh.NbTriangles()
            if count > MAX_TRIANGLES:
                raise ValueError("Model exceeds triangle budget")
            transform = location.Transformation()
            points = np.array(
                [mesh.Node(i).Transformed(transform).Coord() for i in range(1, mesh.NbNodes() + 1)],
                dtype=np.float64,
            )
            indices = np.array(
                [mesh.Triangle(i).Get() for i in range(1, mesh.NbTriangles() + 1)],
                dtype=np.int32,
            ).reshape(-1, 3) - 1
            if face.Orientation() == TopAbs_REVERSED:
                indices = indices[:, [0, 2, 1]]
            triangles.append(points[indices])
        explorer.Next()
    if not triangles:
        raise ValueError("No faces to render")
    result = np.concatenate(triangles)
    if not result.size or not np.isfinite(result).all():
        raise ValueError("Invalid mesh")
    return result


def rasterize(triangles, size):
    """Orthographic isometric camera, barycentric depth test, 2x antialiasing."""
    import numpy as np
    from PIL import Image

    width = size * 2
    low = triangles.min(axis=(0, 1))
    high = triangles.max(axis=(0, 1))
    triangles = (triangles - (low + (high - low) * 0.5)) / max(high - low)
    right = np.array([1, -1, 0]) / math.sqrt(2)
    up = np.array([-1, -1, 2]) / math.sqrt(6)
    forward = np.array([1, 1, 1]) / math.sqrt(3)
    view = triangles @ np.stack([right, -up, forward], axis=1)
    minimum = view[:, :, :2].min(axis=(0, 1))
    maximum = view[:, :, :2].max(axis=(0, 1))
    scale = (width - 1) * 0.84 / max(maximum - minimum)
    view[:, :, :2] = (view[:, :, :2] - (minimum + maximum) / 2) * scale + (width - 1) / 2
    rgba = np.zeros((width, width, 4), dtype=np.uint8)
    normals = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
    lengths = np.linalg.norm(normals, axis=1)
    normals /= np.maximum(lengths[:, None], 1e-20)
    light = np.array([-0.25, -0.5, 1.0])
    light /= np.linalg.norm(light)
    # Two-sided shading also handles open surface STEP models.
    intensity = 0.38 + 0.62 * np.abs(normals @ light)
    colors = np.clip(intensity[:, None] * np.array([108, 172, 222]), 0, 255).astype(np.uint8)
    import ctypes

    library = ctypes.WinDLL(str(Path(__file__).resolve().with_name('StepRaster.dll')))
    draw = library.StepRasterize
    draw.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p]
    draw.restype = ctypes.c_int
    view = np.ascontiguousarray(view, dtype=np.float64)
    if not draw(view.ctypes.data, colors.ctypes.data, len(view), width, rgba.ctypes.data):
        raise ValueError('Native rasterizer failed')
    if not rgba[:, :, 3].any():
        raise ValueError('Model has no visible faces')
    return Image.fromarray(rgba).resize((size, size), Image.Resampling.LANCZOS)


def render(data, size):
    if not 1 <= size <= 1024 or not 0 < len(data) <= MAX_INPUT:
        raise ValueError("Invalid input size")
    if b"ISO-10303-21" not in data[:4096].upper():
        raise ValueError("Expected a STEP Part 21 file")
    return rasterize(tessellate(read_shape(data)), size)


def encode_bgra(image):
    import numpy as np

    rgba = np.array(image, dtype=np.uint8)
    alpha = rgba[:, :, 3:4].astype(np.uint16)
    rgba[:, :, :3] = (rgba[:, :, :3].astype(np.uint16) * alpha + 127) // 255
    return rgba[:, :, [2, 1, 0, 3]].tobytes()


def read_exact(stream, count):
    chunks = []
    remaining = count
    while remaining:
        chunk = stream.read(remaining)
        if not chunk:
            raise EOFError('Truncated renderer request')
        chunks.append(chunk)
        remaining -= len(chunk)
    return b''.join(chunks)


def wait_for_request(stream, idle_ms):
    import ctypes
    from ctypes import wintypes
    import msvcrt

    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    peek = kernel.PeekNamedPipe
    peek.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p,
                     ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
    peek.restype = wintypes.BOOL
    handle = msvcrt.get_osfhandle(stream.fileno())
    deadline = time.monotonic() + idle_ms / 1000
    while time.monotonic() < deadline:
        available = wintypes.DWORD()
        if not peek(handle, None, 0, None, ctypes.byref(available), None):
            code = ctypes.get_last_error()
            if code in (109, 232):  # Parent closed its pipe.
                return False
            raise OSError(code, 'Cannot inspect renderer input')
        if available.value:
            return True
        time.sleep(0.005)
    return False


def serve(stream, output, idle_ms, max_requests):
    for _ in range(max_requests):
        if not wait_for_request(stream, idle_ms):
            return
        magic, size, length = struct.unpack('<4sII', read_exact(stream, 12))
        if magic != b'REQ2' or not 1 <= size <= 1024 or not 0 < length <= MAX_INPUT:
            raise ValueError('Invalid renderer request header')
        data = read_exact(stream, length)
        try:
            image = render(data, size)
            payload = encode_bgra(image)
        except MemoryError:
            output.write(struct.pack('<4sIII', b'STP2', 1, 0, 0))
            output.flush()
            return  # Recycle a process that has exhausted its budget.
        except Exception as error:
            print(f'STEP thumbnail: {error}', file=sys.stderr)
            output.write(struct.pack('<4sIII', b'STP2', 1, 0, 0))
            output.flush()
        else:
            output.write(struct.pack('<4sIII', b'STP2', 0, size, size))
            output.write(payload)
            output.flush()
            del image, payload
        del data


def main():
    parser = argparse.ArgumentParser()
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--pipe', type=int, metavar='SIZE')
    modes.add_argument('--server', action='store_true')
    parser.add_argument('--idle-ms', type=int, default=30000)
    parser.add_argument('--max-requests', type=int, default=32)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--size", type=int, default=256)
    args = parser.parse_args()
    if args.pipe is not None or args.server:
        if not 1 <= args.idle_ms <= 30000 or not 1 <= args.max_requests <= 32:
            parser.error('Invalid worker lifetime limits')
        # OCCT can print diagnostics from C++; keep them out of binary stdout.
        out_fd = os.dup(sys.stdout.fileno())
        os.dup2(sys.stderr.fileno(), sys.stdout.fileno())
        with os.fdopen(out_fd, "wb") as output:
            if args.server:
                serve(sys.stdin.buffer.raw, output, args.idle_ms, args.max_requests)
            else:
                data = sys.stdin.buffer.read(MAX_INPUT + 1)
                image = render(data, args.pipe)
                output.write(struct.pack('<4sII', b'STP1', image.width, image.height))
                output.write(encode_bgra(image))
    else:
        if not args.input or not args.output:
            parser.error("Use --input MODEL.step --output thumbnail.png")
        if args.input.stat().st_size > MAX_INPUT:
            raise ValueError("Model exceeds input budget")
        render(args.input.read_bytes(), args.size).save(args.output)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"STEP thumbnail: {error}", file=sys.stderr)
        sys.exit(1)
