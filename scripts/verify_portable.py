"""Run the real EXE with independent data and Windows-only PATH."""
import argparse
import json
import os
import platform
import subprocess
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("package", type=Path)
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    package = args.package.resolve()
    report = args.report.resolve()
    evidence = report.parent
    sandbox = evidence / (report.stem + "-user")
    sandbox.mkdir(parents=True, exist_ok=True)
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith(
        ("EOJ_", "LLM_", "DEEPSEEK_", "PYTHON", "TCL", "TK", "CXX", "GCC_", "COMPILER_PATH", "LIBRARY_PATH", "CPATH", "CPLUS_INCLUDE_PATH"))}
    env["PATH"] = os.path.join(env["SYSTEMROOT"], "System32") + os.pathsep + env["SYSTEMROOT"]
    env["EOJ_DATA_DIR"] = str(sandbox)
    env["TEMP"] = env["TMP"] = str(sandbox)
    proc = subprocess.run([str(package / "EOJSolver.exe"), "--self-test", str(report), "--gui-smoke"],
                          cwd=sandbox, env=env, timeout=180,
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    result = json.loads(report.read_text(encoding="utf-8"))
    result["platform"] = platform.platform()
    result["process_exit"] = proc.returncode
    result["isolated_path"] = env["PATH"]
    result["acceptance_level"] = "Host process isolation; NOT a clean VM or manual GUI acceptance"
    report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    assert proc.returncode == 0 and result["ok"], result
    assert Path(result["compiler"]["compiler"]).is_relative_to(package), "External compiler used"
    print("Portable process checks passed:", report)


if __name__ == "__main__":
    main()
