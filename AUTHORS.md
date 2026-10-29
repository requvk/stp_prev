# Authors and acknowledgements

## STEP Preview

- **STEP Preview contributors** — subsequent contributions recorded in Git history.
- Initial C/Python implementation, tests and setup scripts were developed with
  assistance from **OpenAI Codex**. This records development provenance; OpenAI
  is not presented as the maintainer or copyright holder.

The original code is covered by [MIT](LICENSE).

## Runtime and build dependencies

| Project | Authors / maintainers credited here | Use |
|---|---|---|
| [Open CASCADE Technology](https://github.com/Open-Cascade-SAS/OCCT) | OPEN CASCADE SAS and contributors | STEP import and tessellation |
| [CadQuery/OCP](https://github.com/CadQuery/OCP) | Bernhard Walter and contributors | Python bindings to OCCT |
| [ocp-build-system](https://github.com/CadQuery/ocp-build-system) | CadQuery contributors; package metadata credits Bernhard Walter | Prebuilt OCP wheels and proxy |
| [CPython](https://github.com/python/cpython) | Python Software Foundation and contributors | Embedded Python |
| [NumPy](https://github.com/numpy/numpy) | NumPy Developers | Arrays, projection, pixel conversion |
| [Pillow](https://github.com/python-pillow/Pillow) | Jeffrey A. Clark and contributors; PIL by Fredrik Lundh and Secret Labs AB | Images and antialiasing |
| [Zig](https://ziglang.org/) | Andrew Kelley and contributors | C compiler, build tool only |

Upstream copyright holders and incorporated components are defined by their
own notices, not just this short table. [THIRD_PARTY.md](THIRD_PARTY.md) records
licenses and the remaining binary redistribution audit.

## Documentation and architecture references

- **Microsoft Corporation** —
  [RecipeThumbnailProvider / Windows-classic-samples](https://github.com/microsoft/Windows-classic-samples/tree/main/Samples/Win7Samples/winui/shell/appshellintegration/RecipeThumbnailProvider).
- **kavabunga6** —
  [STL-3MF-Thumbnail-Preview-Windows / Explorer3DPreview](https://github.com/kavabunga6/STL-3MF-Thumbnail-Preview-Windows).
- **chenxinxinpy** — [stp-thumbnail](https://github.com/chenxinxinpy/stp-thumbnail).

These projects were consulted for COM/Shell design and practical tradeoffs.
Their source files were not copied into this tree. Actual reused binary code
comes from the runtime dependencies listed above.

Real CAD models supplied for local profiling are excluded from this repository,
source archives and example images. Public images use synthetic test geometry
authored for this project.
