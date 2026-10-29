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
C runtime/toolchain code linked into our DLLs still belongs in a binary audit.
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

**Binary release audit is not complete.** The inspected OCP/proxy wheel metadata
directories have no LICENSE/NOTICE files. An Apache text plus the OCCT LGPL texts
is not a complete notice bundle for all DLLs above. Exact component versions,
corresponding notices/source requirements and redistribution permissions must
be verified before publishing a bundled runtime.

Existing local ZIPs are development artifacts. The source repository excludes
them and does not claim their entire contents are MIT. CI does not automatically
publish or upload runtime packages.

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
