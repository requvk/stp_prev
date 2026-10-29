// Bounded CPU z-buffer. This DLL is loaded only by the renderer process.
#include <math.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <windows.h>

__declspec(dllexport) int WINAPI StepRasterize(const double *vertices, const uint8_t *colors,
                                               uint32_t count, uint32_t width, uint8_t *pixels) {
    if (!vertices || !colors || !pixels || !count || count > 200000 || !width || width > 2048) return 0;
    size_t area = (size_t)width * width;
    double *depth = malloc(area * sizeof(*depth));
    if (!depth) return 0;
    memset(pixels, 0, area * 4);
    for (size_t i = 0; i < area; ++i) depth[i] = -INFINITY;
    for (uint32_t i = 0; i < count; ++i) {
        const double *a = vertices + (size_t)i * 9, *b = a + 3, *c = a + 6;
        for (int j = 0; j < 9; ++j) {
            if (!isfinite(a[j])) { free(depth); return 0; }
        }
        double minimum_x = fmin(a[0], fmin(b[0], c[0]));
        double maximum_x = fmax(a[0], fmax(b[0], c[0]));
        double minimum_y = fmin(a[1], fmin(b[1], c[1]));
        double maximum_y = fmax(a[1], fmax(b[1], c[1]));
        if (maximum_x < 0 || maximum_y < 0 || minimum_x > width - 1 || minimum_y > width - 1) continue;
        int x0 = (int)fmax(0, floor(minimum_x));
        int x1 = (int)fmin(width - 1, ceil(maximum_x));
        int y0 = (int)fmax(0, floor(minimum_y));
        int y1 = (int)fmin(width - 1, ceil(maximum_y));
        double determinant = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1]);
        if (fabs(determinant) < 1e-12) continue;
        double inverse = 1.0 / determinant;
        for (int y = y0; y <= y1; ++y) {
            for (int x = x0; x <= x1; ++x) {
                double u = ((b[1] - c[1]) * (x - c[0]) + (c[0] - b[0]) * (y - c[1])) * inverse;
                double v = ((c[1] - a[1]) * (x - c[0]) + (a[0] - c[0]) * (y - c[1])) * inverse;
                double w = 1.0 - u - v;
                if (u < -1e-8 || v < -1e-8 || w < -1e-8) continue;
                double z = u * a[2] + v * b[2] + w * c[2];
                size_t offset = (size_t)y * width + x;
                if (z <= depth[offset]) continue;
                depth[offset] = z;
                uint8_t *pixel = pixels + offset * 4;
                memcpy(pixel, colors + (size_t)i * 3, 3);
                pixel[3] = 255;
            }
        }
    }
    free(depth);
    return 1;
}
