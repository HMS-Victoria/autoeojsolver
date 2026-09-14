# -*- coding: utf-8 -*-
"""GUI 冒烟测试：真实构建 Tk 界面 → 泵事件 → 调用关键回调 → 销毁。

覆盖点（都是旧版踩过坑的地方）：

* 供应商下拉框切换后 ``base_url`` / 模型候选是否精确等于该预设的值
* 日志 sink 是否真的接到 GUI 队列上
* ``push_config_to_engine()`` 把界面配置写回 ``engine`` 全局变量
* ``toggle_api_key()`` 不再引用不存在的控件（v3 的 AttributeError 回归测试）
* ``save_config()`` / ``load_config()`` 往返不丢字段

配置读写全部被重定向到 ``tmp_path``：既不污染仓库里的 ``eoj_config.json``，
也让每个用例从干净配置起步（否则上一次运行留下的供应商选择会让断言失去意义）。
没有 Tk 或没有显示环境（无头 CI / Linux 无 X）时自动跳过。
"""

from __future__ import annotations

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

tk = pytest.importorskip("tkinter", reason="需要 tkinter")


def _make_root():
    try:
        root = tk.Tk()
    except tk.TclError as exc:  # 无显示环境
        pytest.skip(f"无法创建 Tk 窗口: {exc}")
    root.withdraw()  # 不要闪窗
    root.update_idletasks()
    return root


def test_gui_constructs_and_callbacks_do_not_raise(tmp_path, monkeypatch):
    """构建主窗口并逐个触发关键回调，任何异常都算失败。"""
    import eojstart

    sandbox_cfg = tmp_path / "eoj_config.json"
    sandbox_legacy = tmp_path / "eoj_gui_config.json"

    monkeypatch.setattr(eojstart, "CONFIG_FILE", str(sandbox_cfg), raising=False)
    monkeypatch.setattr(eojstart, "LEGACY_CONFIG_FILE", str(sandbox_legacy), raising=False)

    # 引擎侧配置读写同样落到 sandbox（否则 save_config() 会写到仓库根目录）
    def fake_save(config):
        sandbox_cfg.write_text(
            json.dumps(config or {}, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return str(sandbox_cfg)

    monkeypatch.setattr(eojstart.engine, "save_gui_config", fake_save, raising=False)
    monkeypatch.setattr(
        eojstart.engine,
        "load_gui_config",
        lambda: json.loads(sandbox_cfg.read_text(encoding="utf-8"))
        if sandbox_cfg.is_file()
        else {},
        raising=False,
    )

    root = _make_root()
    try:
        app = eojstart.EOJGUI(root)
        for _ in range(30):
            root.update()
        root.update_idletasks()

        # --- 配置区初值 ---
        assert app.var_provider.get()
        assert app.var_base_url.get()
        assert app.var_model.get()
        assert len(app.combo_model.cget("values")) >= 1
        assert len(app.combo_provider.cget("values")) >= 1

        # --- 兼容层是否仍然暴露历史全局变量 ---
        assert eojstart.engine.DEEPSEEK_MODEL

        # --- 日志 sink 接线 ---
        eojstart.engine.set_log_sink(app._enqueue_log)
        assert eojstart.engine.get_log_sink() is not None
        eojstart.engine.log_ok("gui sink smoke test")
        root.update()
        drained = 0
        while not app.msg_queue.empty():
            app.msg_queue.get_nowait()
            drained += 1
        assert drained >= 1

        # --- 切换供应商：接入点与候选模型必须精确等于该预设 ---
        from eojkit.config import PROVIDER_PRESETS

        ollama = PROVIDER_PRESETS["ollama"]
        app.var_provider.set("ollama - 本地 Ollama")
        app.on_provider_change()
        root.update()
        assert app.var_base_url.get() == ollama["base_url"]
        assert app.var_model.get() in ollama["models"]
        assert list(app.combo_model.cget("values")) == list(ollama["models"])

        # --- 配置写回 engine ---
        app.push_config_to_engine()
        assert eojstart.engine.LLM_BASE_URL == ollama["base_url"].rstrip("/")

        # --- v3 回归：toggle 两次不得抛异常 ---
        app.toggle_api_key()
        app.toggle_api_key()

        # --- 配置往返（写入 sandbox，不碰真实配置） ---
        app.save_config()
        assert sandbox_cfg.is_file()
        loaded = app.load_config()
        assert isinstance(loaded, dict)
        assert loaded.get("provider") == "ollama"
        assert loaded.get("base_url") == ollama["base_url"]
        assert loaded.get("model") == app.var_model.get()
    finally:
        try:
            root.destroy()
        except Exception:  # noqa: BLE001
            pass


if __name__ == "__main__":  # 允许 python tests/test_gui_smoke.py 直接跑
    import tempfile

    from _pytest.monkeypatch import MonkeyPatch

    with tempfile.TemporaryDirectory() as tmp:
        mp = MonkeyPatch()
        try:
            test_gui_constructs_and_callbacks_do_not_raise(
                __import__("pathlib").Path(tmp), mp
            )
        finally:
            mp.undo()
    print("GUI SMOKE TEST PASSED")
