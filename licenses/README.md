# Third-party notices and source availability

The MIT license at the project root covers STEP Preview's own code.
Bundled libraries keep their original licenses. Read [THIRD_PARTY.md](../THIRD_PARTY.md)
and the component notices in this directory.

The distribution includes CPython's `runtime/LICENSE.txt` and the original
NumPy/Pillow wheel notices under `runtime/Lib/site-packages/*dist-info/licenses/`.
Additional native component notices are supplied in `native/`; `native/inventory.json`
records the original packages and SHA256 hashes. MinGW-w64 and delvewheel notices
are also preserved here.

## Corresponding source materials

Download **StepPreview-1.0.0-third-party-sources.zip** from the
[same release](https://github.com/requvk/stp_prev/releases/tag/v1.0.0).
It is available without charge and is not needed to install or run STEP Preview.
It contains the upstream source archives for OCCT 7.9.3, LibRaw 0.21.5,
LibRaw's CMake support and FreeImage 3.18.0, the pinned OCP build system,
and the matching FreeImage/LibRaw build recipes and patches.
The archive includes source checksums and origin URLs.

OCCT is provided under LGPL 2.1 with the OCCT exception. LibRaw is provided
under its LGPL 2.1 option. FreeImage is provided under its FreeImage Public
License option. Alternative license texts preserved upstream do not change
these selections. Consult the complete component texts for their conditions.

The OCP build-system archive contains the OCCT build commands and source patch.
The conda recipes contain the FreeImage/LibRaw patches and compiler configuration.
The wheel uses delvewheel to rewrite dependency names; the library algorithms
were not modified by STEP Preview. Exact wheel versions are in
`renderer/requirements.txt` in the source repository.

## Replacing dynamic libraries

The bundled OCCT/LibRaw DLLs are separate dynamic libraries in
`runtime/Lib/site-packages/cadquery_ocp_novtk.libs/`. There is no cryptographic
restriction on replacing them. Replacement builds must preserve the expected
ABI, exported symbols and dependency filenames, or the wheel and its dependency
tables must be rebuilt/repaired together using the supplied build configuration.
Work on an unpacked copy, verify rendering, then reinstall from that copy.

STEP Preview's MIT terms do not restrict reverse engineering or modification
for debugging replacement LGPL libraries. Microsoft runtime files remain
subject to their separate Microsoft terms.
