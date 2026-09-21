"""Zip the verified candidate and check it after relocation."""
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs/release-readiness/2026-09-20"


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--verification-dir", type=Path, default=ROOT / "build/msys2 relocated acceptance")
    args = parser.parse_args()
    relocated = args.verification_dir.resolve()
    if (relocated / "EOJSolver").exists():
        raise SystemExit("Use a fresh verification directory; existing acceptance files are retained.")
    package = ROOT / "dist/EOJSolver"
    release = ROOT / "release"
    release.mkdir(exist_ok=True)
    assert json.loads((DOCS / "portable-selftest.json").read_text(encoding="utf-8"))["ok"]
    upstream = ROOT / "build/msys2-toolchain/ucrt64"
    assert {p.relative_to(upstream) for p in upstream.rglob("*") if p.is_file()} == {p.relative_to(package / "toolchain/ucrt64") for p in (package / "toolchain/ucrt64").rglob("*") if p.is_file()}, "Toolchain file set differs"
    integrity = {}
    for source in sorted(upstream.rglob("*")):
        if source.is_file():
            relative = source.relative_to(upstream)
            expected = digest(source)
            assert digest(package / "toolchain/ucrt64" / relative) == expected, relative
            integrity[str(relative)] = expected
    (DOCS / "toolchain-integrity.json").write_text(json.dumps({"files_verified": len(integrity), "files": integrity}, indent=2), encoding="utf-8")
    for name in ("USER_GUIDE.md", "RELEASE_NOTES.md", "THIRD_PARTY.md"):
        shutil.copy2(DOCS / name, release / name)
    shutil.copy2(package / "SOURCE_MANIFEST.json", release / "SOURCE_MANIFEST.json")
    archive = release / "EOJSolver-4.0.1-windows-x64-candidate.zip"
    forbidden = {"eoj_config.json", "eoj_gui_config.json", ".env", "captcha_tmp.png"}
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=5) as output:
        for file in sorted(package.rglob("*")):
            if file.is_file():
                relative = file.relative_to(package)
                assert file.name not in forbidden, relative
                assert relative.parts[0] not in {"solutions", "eoj_solutions", "research", "build", "docs", ".git"}, relative
                output.write(file, Path("EOJSolver") / relative)
    relocated.mkdir(exist_ok=True)
    with zipfile.ZipFile(archive) as zipped:
        assert zipped.testzip() is None
        zipped.extractall(relocated)
        file_count = len(zipped.namelist())
    subprocess.run([sys.executable, str(ROOT / "scripts/verify_portable.py"),
                    str(relocated / "EOJSolver"), str(DOCS / "relocated-selftest.json")], check=True)
    (DOCS / "package-audit.json").write_text(json.dumps({
        "asset": archive.name, "bytes": archive.stat().st_size, "sha256": digest(archive),
        "zip_members": file_count, "zip_crc_check": "pass", "toolchain_files_verified": len(integrity),
        "excluded_user_data_check": "pass", "relocated_selftest": "pass",
    }, indent=2), encoding="utf-8")
    print("Verified candidate ZIP:", archive, flush=True)


if __name__ == "__main__":
    main()
