# Third-party components and provenance

The original STEP Preview sources are under [MIT](LICENSE). Dependencies retain
their own licenses. This inventory describes the pinned development configuration.
See [AUTHORS.md](AUTHORS.md) for credits. Verify the complete dependency inventory
and required notices below before distributing binaries.

## Direct runtime dependencies

| Component | Version | Upstream / authors | License and notices |
|---|---|---|---|
| CPython Embedded x64 | 3.14.4 | [Python Software Foundation and contributors](https://www.python.org/) | PSF License and incorporated notices; `runtime/LICENSE.txt` in a built package |
| cadquery-ocp-novtk | 7.9.3.1.1 | [CadQuery/OCP](https://github.com/CadQuery/OCP), Bernhard Walter and contributors | Apache-2.0; [saved text](licenses/OCP-LICENSE) |
| cadquery-ocp-proxy | 7.9.3.1.1 | [CadQuery/ocp-build-system](https://github.com/CadQuery/ocp-build-system), CadQuery contributors | Apache-2.0 according to package metadata; no separate license file in the inspected wheel |
| Open CASCADE Technology | 7.9.3 | [OPEN CASCADE SAS and contributors](https://github.com/Open-Cascade-SAS/OCCT/tree/V7_9_3) | [LGPL 2.1](licenses/OCCT-LICENSE_LGPL_21.txt) with [OCCT exception](licenses/OCCT-EXCEPTION.txt) |
| NumPy | 2.4.2 | [NumPy Developers](https://github.com/numpy/numpy) | BSD-3-Clause; wheel includes further notices in `numpy-*.dist-info/licenses/` |
| Pillow | 12.1.1 | [Pillow contributors](https://github.com/python-pillow/Pillow); Jeffrey A. Clark, Fredrik Lundh, Secret Labs AB | MIT-CMU; wheel's `pillow-*.dist-info/licenses/LICENSE` includes bundled component notices |

OCP metadata names Bernhard Walter as author; see the
[pinned PyPI package](https://pypi.org/project/cadquery-ocp-novtk/7.9.3.1.1/).
OCCT and its native dependencies come from that wheel. STEP Preview does not
build or modify those upstream libraries. Upstream packaging includes changes
such as renamed native libraries made by delvewheel.

## Build tools

[Zig 0.14.1](https://ziglang.org/), by Andrew Kelley and contributors, is used
as a C compiler. Zig's MIT license and its toolchain notices apply to the tool
distribution. The compiler distribution is not copied into the runtime package.
MinGW-w64 runtime notices for the Windows GNU target accompany our DLLs in
[MinGW-w64-COPYING](licenses/MinGW-w64-COPYING).
GitHub Actions actions are fetched by CI, not included in the runtime package.

## Additional native libraries in the OCP wheel

The inspected Windows x64 wheel contains these DLL families in
`cadquery_ocp_novtk.libs/`:

- OCCT `TK*` and `TKernel`;
- FreeImage, FreeType, libdeflate;
- OpenEXR / Iex / IlmThread, Imath;
- libjpeg, Little CMS, Lerc, liblzma / XZ;
- libpng, libwebp / libwebpmux / libsharpyuv;
- OpenJPEG, OpenJPH, LibRaw, libtiff;
- zlib, Zstandard;
- Microsoft C++ / OpenMP runtimes (`msvcp140`, `vcomp140`).

These are actual bundled dependencies, including libraries not directly called
by our renderer. They do not automatically share OCP's Apache license.

The upstream OCP/proxy wheel metadata directories omit LICENSE/NOTICE files.
STEP Preview therefore adds the upstream OCP/OCCT texts and the native component
notices in [licenses/native/](licenses/native). The
[inventory](licenses/native/inventory.json) records exact conda package versions,
package hashes and hashes of the 24 additional native DLLs. Their provenance was
verified against the original binaries using the dependency-aware name hashes
inserted by delvewheel. This does not mean all dependencies are MIT.

| Native component | Verified version | License selection / notices |
|---|---|---|
| FreeImage | 3.18.0 | FreeImage Public License; alternative GPL texts preserved |
| FreeType | 2.12.1 | FreeType License; alternative GPL text preserved |
| libdeflate | 1.25 | MIT |
| OpenEXR / Iex / IlmThread | 3.4.12 | BSD-3-Clause |
| Imath | 3.2.2 | BSD-3-Clause |
| libjpeg-turbo | 3.1.4.1 | IJG, BSD and zlib notices in its saved LICENSE |
| Little CMS | 2.19.1 | MIT |
| Lerc | 4.1.0 | Apache-2.0 |
| liblzma / XZ | 5.8.3 | 0BSD for liblzma; upstream COPYING included |
| libpng | 1.6.58 | libpng license |
| libwebp / libwebpmux / libsharpyuv | 1.6.0 | BSD-3-Clause |
| OpenJPEG | 2.5.4 | BSD-2-Clause |
| OpenJPH | 0.27.3 | BSD-2-Clause |
| LibRaw | 0.21.5 | LGPL-2.1 selection; alternative CDDL text preserved |
| libtiff | 4.7.1 | libtiff license |
| zlib | 1.3.2 | Zlib |
| Zstandard | 1.5.7 | BSD-3-Clause |
| Microsoft C++ / OpenMP runtime | 14.51.36231 | Microsoft terms, including the original RTF notice |

Little CMS still reports 2.19.0 in its Windows version resource; the original
binary hash identifies the package as 2.19.1. SharpYUV's numeric API version
is not the libwebp package version.

OCCT 7.9.3 is built by the pinned
[ocp-build-system v7.9.3.1.1](https://github.com/CadQuery/ocp-build-system/tree/v7.9.3.1.1),
including its CMake-order patch. It is not the conda-forge OCCT binary package.
OCP's loader uses delvewheel 1.12.1; its
[MIT notice](licenses/Delvewheel-LICENSE) is included.

The same GitHub release provides `StepPreview-1.0.0-third-party-sources.zip`:
OCCT V7_9_3, LibRaw 0.21.5 plus its CMake build sources, FreeImage 3.18.0,
the pinned OCP build system and the matching FreeImage/LibRaw conda build recipes
and patches. See [source availability and replacement](licenses/README.md).

CI builds and tests the package; publication is a separate explicit operation.

## Examples studied during development

- [Microsoft Windows-classic-samples](https://github.com/microsoft/Windows-classic-samples),
  Microsoft Corporation: COM interfaces, reference counting and isolation; MIT
  at repository level.
- [Explorer3DPreview](https://github.com/kavabunga6/STL-3MF-Thumbnail-Preview-Windows),
  kavabunga6: input limits and restoring previous registrations as design references.
- [stp-thumbnail](https://github.com/chenxinxinpy/stp-thumbnail), chenxinxinpy:
  an example of separating a Shell DLL and a rendering process.

No source files from these three examples were vendored into this tree.
Our implementation, scripts and tests were written for STEP Preview with AI
assistance. The links above identify the design references.
