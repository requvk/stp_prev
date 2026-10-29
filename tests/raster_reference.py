import math

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
    depth = np.full((width, width), -np.inf, dtype=np.float64)
    rgba = np.zeros((width, width, 4), dtype=np.uint8)
    normals = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
    lengths = np.linalg.norm(normals, axis=1)
    normals /= np.maximum(lengths[:, None], 1e-20)
    light = np.array([-0.25, -0.5, 1.0])
    light /= np.linalg.norm(light)
    # Two-sided shading also handles open surface STEP models.
    intensity = 0.38 + 0.62 * np.abs(normals @ light)
    colors = np.clip(intensity[:, None] * np.array([108, 172, 222]), 0, 255).astype(np.uint8)
    for triangle, color in zip(view, colors):
        x0 = max(0, math.floor(triangle[:, 0].min()))
        x1 = min(width - 1, math.ceil(triangle[:, 0].max()))
        y0 = max(0, math.floor(triangle[:, 1].min()))
        y1 = min(width - 1, math.ceil(triangle[:, 1].max()))
        if x1 < x0 or y1 < y0:
            continue
        a, b, c = triangle
        denominator = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
        if abs(denominator) < 1e-12:
            continue
        y, x = np.ogrid[y0 : y1 + 1, x0 : x1 + 1]
        u = ((b[1] - c[1]) * (x - c[0]) + (c[0] - b[0]) * (y - c[1])) / denominator
        v = ((c[1] - a[1]) * (x - c[0]) + (a[0] - c[0]) * (y - c[1])) / denominator
        w = 1 - u - v
        z = u * a[2] + v * b[2] + w * c[2]
        patch = depth[y0 : y1 + 1, x0 : x1 + 1]
        mask = (u >= -1e-8) & (v >= -1e-8) & (w >= -1e-8) & (z > patch)
        patch[mask] = z[mask]
        pixels = rgba[y0 : y1 + 1, x0 : x1 + 1]
        pixels[mask, :3] = color
        pixels[mask, 3] = 255
    if not rgba[:, :, 3].any():
        raise ValueError("Model has no visible faces")
    return Image.fromarray(rgba).resize((size, size), Image.Resampling.LANCZOS)
