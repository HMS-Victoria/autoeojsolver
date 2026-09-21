# Third-party materials

Application: MIT. Bundled native compiler: MSYS2 UCRT MinGW-w64 GCC 16.2.0-3 and the complete runtime dependency closure (17 official packages). Original package payloads are unchanged; their ucrt64 prefix is relocated to toolchain/ucrt64. No global installation or PATH change is required.

Official package: https://packages.msys2.org/packages/mingw-w64-ucrt-x86_64-gcc
Official binary/source repository: https://repo.msys2.org/mingw/

MSYS2_TOOLCHAIN_MANIFEST.json records every version, license expression, official binary SHA256, source archive hash and dependency. The paired EOJSolver-4.0.1-toolchain-sources.zip contains 15 full source-only packages, original sources (or pinned Git repositories), patches, PKGBUILD build recipes, .SRCINFO and package metadata. Publish this source asset alongside the GUI ZIP and retain both together. It is separate from the application source ZIP. Source checking is documented in MSYS2_SOURCE_VERIFICATION.json; no claim of a reproducible byte-identical compiler rebuild is made.

Compiler licenses include GPL, LGPL with applicable GCC runtime exception, and other component licenses. Existing notices remain in toolchain/ucrt64/share/licenses; supplementary license text is in licenses/toolchain. Application licensing does not replace component licensing. Python dependency notices, Python, Tcl and Tk notices are included under licenses. Exact Python build dependencies are recorded in requirements-build.lock. Publication was authorized by the repository owner on 2026-09-21. This prerelease must be distributed with its matching toolchain source companion; clean-machine and visible GUI acceptance remain pending.

Earlier WinLibs experiments and their incomplete source-matching review are historical build evidence only and are not used in this candidate.
