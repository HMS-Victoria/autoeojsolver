"""Build only allowlisted application sources; never copy user data."""
import argparse
import hashlib
import importlib.metadata
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--toolchain", type=Path, required=True, help="Complete verified mingw64 directory")
    args = parser.parse_args()
    import tkinter
    tkinter.Tcl()  # Fail before packaging if Tcl/Tk cannot be initialized.
    chain = args.toolchain.resolve()
    for required in ("bin/g++.exe", "include", "lib", "share", "x86_64-w64-mingw32"):
        if not (chain / required).exists():
            raise SystemExit("Incomplete toolchain: " + required)
    subprocess.run([
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed", "--onedir",
        "--name", "EOJSolver", "--specpath", "build", "--distpath", "dist",
        "--collect-all", "ddddocr", "--collect-all", "onnxruntime", "--collect-all", "Crypto",
        "--exclude-module", "pytest", "eoj_portable.py",
    ], cwd=ROOT, check=True)
    package = ROOT / "dist/EOJSolver"
    shutil.copytree(chain, package / "toolchain/ucrt64", dirs_exist_ok=True)
    licenses = package / "licenses"
    licenses.mkdir(exist_ok=True)
    shutil.copy2(ROOT / "LICENSE", licenses / "EOJSolver-MIT.txt")
    for dist in importlib.metadata.distributions():
        target = licenses / (dist.metadata["Name"] + "-" + dist.version)
        for file in dist.files or []:
            if any(word in file.name.lower() for word in ("license", "copying", "notice")):
                source = Path(dist.locate_file(file))
                if source.is_file():
                    destination = target / str(file).replace("..", "parent")
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, destination)
    for name, path in (("Python", Path(sys.base_prefix) / "LICENSE.txt"),
                       ("Tcl", Path(sys.base_prefix) / "tcl/tcl8.6/license.terms"),
                       ("Tk", Path(sys.base_prefix) / "tcl/tk8.6/license.terms")):
        if path.is_file():
            shutil.copy2(path, licenses / (name + ".txt"))
    shutil.copy2(ROOT / "docs/release-readiness/2026-09-20/USER_GUIDE.md", package / "使用说明.txt")
    shutil.copy2(ROOT / "docs/release-readiness/2026-09-20/THIRD_PARTY.md", licenses / "THIRD_PARTY.md")
    shutil.copy2(ROOT / "docs/release-readiness/2026-09-20/TOOLCHAIN_SOURCE.json", licenses / "toolchain-source.json")
    shutil.copytree(ROOT / "docs/release-readiness/2026-09-20/third-party-licenses", licenses / "toolchain", dirs_exist_ok=True)
    shutil.copy2(ROOT / "docs/release-readiness/2026-09-20/MSYS2_TOOLCHAIN_MANIFEST.json", licenses / "MSYS2_TOOLCHAIN_MANIFEST.json")
    files = [ROOT / n for n in ("eojstart.py", "eoj_auto_solver.py", "eoj_portable.py", "requirements.txt", "LICENSE")]
    files += sorted((ROOT / "eojkit").rglob("*.py"))
    manifest = {str(p.relative_to(ROOT)).replace("\\", "/"): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    (package / "SOURCE_MANIFEST.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print("Package assembled at", package)


if __name__ == "__main__":
    main()
