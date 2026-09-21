"""Windowed portable entry; explicit offline diagnostics for release QA."""
import argparse
import json
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", type=Path)
    parser.add_argument("--gui-smoke", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        report = {"frozen": bool(getattr(sys, "frozen", False)), "ok": False}
        try:
            from eojkit.portable import local_check, offline_pipeline_check
            report["compiler"] = local_check()
            report["pipeline"] = offline_pipeline_check()
            import requests, bs4, PIL, Crypto, ddddocr
            ddddocr.DdddOcr(show_ad=False)
            report["dependencies"] = True
            if args.gui_smoke:
                import tkinter as tk
                import eojstart
                root = tk.Tk()
                root.withdraw()
                app = eojstart.EOJGUI(root)
                root.update()
                report["gui"] = {"constructed": True, "submit_default": app.var_submit.get()}
                root.destroy()
            report["ok"] = report["compiler"]["ok"] and all(report["pipeline"].values()) and not report.get("gui", {}).get("submit_default", False)
        except Exception:
            import traceback
            report["error"] = traceback.format_exc()
        args.self_test.parent.mkdir(parents=True, exist_ok=True)
        args.self_test.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return 0 if report["ok"] else 1
    from eojkit.paths import DATA_DIR
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    import eojstart
    eojstart.main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
