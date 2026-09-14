#!/usr/bin/env python3
"""
EOJ 自动刷题系统 - 图形界面 v3.1
====================================
Tkinter 桌面窗口程序，作为 eoj_auto_solver.py 的前端交互界面。
支持题目浏览、选择、批量刷题。

Designed by HMS_Victorious

用法:
  python eoj_gui.py          # 直接启动窗口程序
"""

import sys
import os
import json
import time
import threading
import queue
import io
import re
from tkinter import *
from tkinter import ttk, messagebox, filedialog, scrolledtext
from PIL import Image, ImageTk

# ============================================================
# 导入核心引擎
# ============================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import eoj_auto_solver as engine
from eojkit.config import PROVIDER_PRESETS, SOLUTIONS_DIRNAME, get_settings

# ============================================================
# 配置
# ============================================================
# v4.0：配置文件迁到 eoj_config.json（含旧 eoj_gui_config.json 自动迁移），
# 并且**不再在源码里硬编码任何账号/密码/API Key** —— 请用环境变量
# （EOJ_USERNAME / EOJ_PASSWORD / DEEPSEEK_API_KEY）或直接在界面填写。
CONFIG_FILE = os.path.join(BASE_DIR, 'eoj_config.json')
LEGACY_CONFIG_FILE = os.path.join(BASE_DIR, 'eoj_gui_config.json')

#: 模型下拉框兜底候选（真实清单由 GET /models 探测，见 refresh_models()）
DEFAULT_MODELS = ['deepseek-v4-pro', 'deepseek-flash']

DEFAULT_CONFIG = {
    'username': '',
    'password': '',
    'api_key': '',
    'solutions_dir': os.path.join(BASE_DIR, SOLUTIONS_DIRNAME),
    'remember': True,
    'model': DEFAULT_MODELS[0],
    'base_url': PROVIDER_PRESETS['deepseek']['base_url'],
    'provider': 'deepseek',
    'timeout': 0,  # 单题超时秒数，0=不限时
}


# ============================================================
# 日志重定向 - 把 print 输出捕获到 GUI
# ============================================================

class TextRedirector(io.StringIO):
    """将 print 输出重定向到 Tkinter Text 控件 + Queue"""
    def __init__(self, text_widget, msg_queue):
        super().__init__()
        self.text_widget = text_widget
        self.msg_queue = msg_queue

    def write(self, msg):
        if msg and msg != '\n':
            self.msg_queue.put(msg)
        if msg.strip():
            try:
                sys.__stdout__.write(msg)
                sys.__stdout__.flush()
            except:
                pass

    def flush(self):
        try:
            sys.__stdout__.flush()
        except:
            pass


# ============================================================
# 主窗口
# ============================================================

class EOJGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("EOJ 自动刷题系统 v3.1 — Designed by HMS_Victorious")
        self.root.geometry("1000x760")
        self.root.minsize(850, 650)

        # 保存引用以便验证码弹窗访问
        import __main__
        __main__._eoj_gui_app = self

        # 注入 GUI 的 solve_captcha
        engine.solve_captcha = self._gui_solve_captcha
        # 注入确认回调（样例不通过时弹窗，避免 input() 崩溃）
        engine.CONFIRMATION_CALLBACK = self._gui_confirm

        # 运行状态
        self.running = False
        self.stop_flag = False

        # EOJ 客户端引用（共享登录状态）
        self.eoj_client = None

        # 日志队列
        self.msg_queue = queue.Queue()
        self.log_buffer = []

        # 日志级别: 'normal' = 显示全部, 'simple' = 仅显示关键信息
        self.var_log_level = StringVar(value='simple')

        # 加载配置
        self.config = self.load_config()

        # 缓存题目列表（来自网站浏览）
        self.problem_cache = []       # 全量列表
        self.selected_problems = set()  # 用户已勾选的题号

        # 竞赛模式相关
        self.contest_problems = []     # 竞赛题目列表
        self.contest_id = ''           # 当前竞赛ID
        self.selected_contest_problems = set()  # 竞赛模式已勾选的题目
        self.contest_verdict_cache = {}  # {'cid:pid': 'AC'|'WA'|etc}
        self.contest_verdict_cache_time = {}  # {'cid:pid': timestamp}

        # 创建 UI
        self.create_widgets()

        # 启动日志轮询
        self.poll_log_queue()

        # 窗口关闭处理
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    # ----------------------------------------------------------
    # 验证码弹窗
    # ----------------------------------------------------------

    def _gui_solve_captcha(self, image_data):
        """替换 engine.solve_captcha，用 GUI 弹窗处理验证码"""
        result = engine.try_ocr_captcha(image_data)
        if result:
            return result

        captcha_result = [None]
        event = threading.Event()

        def show_dialog():
            dialog = CaptchaDialog(self.root, image_data)
            self.root.wait_window(dialog)
            captcha_result[0] = dialog.result
            event.set()

        self.root.after(0, show_dialog)
        event.wait()
        return captcha_result[0] or ''

    def _gui_confirm(self, prompt):
        """替换 input()，用 GUI 弹窗询问用户"""
        result = [False]
        event = threading.Event()

        def show_dialog():
            r = messagebox.askyesno("确认", prompt + "\n\n继续提交?")
            result[0] = r
            event.set()

        self.root.after(0, show_dialog)
        event.wait()
        return result[0]

    # ----------------------------------------------------------
    # 配置管理
    # ----------------------------------------------------------

    def load_config(self):
        """读取配置：环境变量 > eoj_config.json（自动迁移旧文件）> 默认值。"""
        cfg = DEFAULT_CONFIG.copy()
        # 引擎这边已经做了 .env / 环境变量 / JSON 的分层合并，直接复用同一份真相。
        # 注意：不再直接读旧 eoj_gui_config.json —— 引擎在迁移时会读它一次并写出
        # eoj_config.json，如果这里再叠加一次旧文件，会把用户已更新的模型/接入点
        # 又覆盖回旧值（实测踩过：GUI 显示 deepseek-v4-flash）。
        try:
            cfg.update({k: v for k, v in engine.load_gui_config().items() if v not in (None, '')})
        except Exception as exc:
            print(f"[WARN] 读取引擎配置失败: {exc}")
        # 仅当新配置文件缺失时，才把旧文件当作最后兜底
        if not os.path.exists(CONFIG_FILE) and os.path.exists(LEGACY_CONFIG_FILE):
            try:
                with open(LEGACY_CONFIG_FILE, 'r', encoding='utf-8') as f:
                    legacy = json.load(f)
                for key, value in legacy.items():
                    if cfg.get(key) in (None, ''):
                        cfg[key] = value
            except Exception:
                pass
        return cfg

    @staticmethod
    def _provider_key(display_value):
        """把 "ollama — 本地 Ollama" 这样的下拉显示值还原成键名 "ollama"。"""
        raw = (display_value or "").strip()
        for separator in (' — ', ' - '):
            if separator in raw:
                raw = raw.split(separator)[0]
        return raw.strip() or 'deepseek'

    def save_config(self):
        try:
            cfg = {
                'username': self.entry_username.get().strip(),
                'password': self.entry_password.get().strip(),
                'api_key': self.entry_apikey.get().strip(),
                'solutions_dir': self.config.get('solutions_dir', engine.DEFAULT_SOLUTIONS_DIR),
                'remember': self.var_remember.get(),
                'model': self.var_model.get(),
                'base_url': self.var_base_url.get().strip(),
                'provider': self._provider_key(self.var_provider.get()),
                'timeout': self.var_timeout.get()
            }
            # 交给引擎统一落盘（原子写入 + 不记住密码时自动剔除）
            engine.save_gui_config(cfg)
        except Exception as e:
            print(f"[WARN] 保存配置失败: {e}")

    def _enqueue_log(self, text):
        """引擎日志出口：投递到 GUI 日志队列。

        与旧版 ``sys.stdout`` 重定向相比，这条路径不依赖全局 stdout，
        因此多个工作线程并发输出时不会互相覆盖，也不受 GIL 写竞争影响。
        """
        if text is None:
            return
        try:
            self.msg_queue.put(str(text))
            sys.__stdout__.write(str(text) + "\n")
        except Exception:
            pass

    def push_config_to_engine(self):
        """把界面上的值推给引擎（任务开始前 / 测试连接前调用）。"""
        engine.sync_runtime_settings(
            username=self.entry_username.get().strip(),
            password=self.entry_password.get().strip(),
            api_key=self.entry_apikey.get().strip(),
            model=self.var_model.get().strip(),
            base_url=self.var_base_url.get().strip(),
            provider=self._provider_key(self.var_provider.get()),
            solutions_dir=self.config.get('solutions_dir', None),
        )

    # ----------------------------------------------------------
    # 创建界面
    # ----------------------------------------------------------

    def create_widgets(self):
        # ========== 主框架 ==========
        main_frame = ttk.Frame(self.root, padding="5")
        main_frame.pack(fill=BOTH, expand=True)

        # ========== 顶部标题 ==========
        title_frame = ttk.Frame(main_frame)
        title_frame.pack(fill=X, pady=(0, 5))

        title_label = Label(title_frame, text="⭐ EOJ 自动刷题系统",
                           font=("微软雅黑", 16, "bold"), fg="#1a73e8")
        title_label.pack(side=LEFT)

        status_frame = ttk.Frame(title_frame)
        status_frame.pack(side=RIGHT)
        self.lbl_status = Label(status_frame, text="状态: 就绪",
                                font=("微软雅黑", 10), fg="#666")
        self.lbl_status.pack(side=LEFT)

        # ========== 配置面板（全局） ==========
        cfg_frame = ttk.LabelFrame(main_frame, text="📋 账号配置", padding="8")
        cfg_frame.pack(fill=X, pady=(0, 5))

        ttk.Label(cfg_frame, text="用户名:", width=10).grid(row=0, column=0, sticky=W, pady=2)
        self.entry_username = ttk.Entry(cfg_frame, width=40, font=("微软雅黑", 9))
        self.entry_username.grid(row=0, column=1, sticky=EW, pady=2, padx=5)
        self.entry_username.insert(0, self.config.get('username', ''))

        ttk.Label(cfg_frame, text="密码:", width=10).grid(row=0, column=2, sticky=W, pady=2, padx=(10, 0))
        self.entry_password = ttk.Entry(cfg_frame, width=20, font=("微软雅黑", 9), show="*")
        self.entry_password.grid(row=0, column=3, sticky=EW, pady=2, padx=5)
        self.entry_password.insert(0, self.config.get('password', ''))

        ttk.Label(cfg_frame, text="API Key:", width=9).grid(row=0, column=4, sticky=W, pady=2, padx=(10, 0))
        self.entry_apikey = ttk.Entry(cfg_frame, width=25, font=("微软雅黑", 9), show="*")
        self.entry_apikey.grid(row=0, column=5, sticky=EW, pady=2, padx=5)
        self.entry_apikey.insert(0, self.config.get('api_key', ''))
        ttk.Button(cfg_frame, text="👁", width=3, command=self.toggle_api_key).grid(
            row=0, column=6, sticky=W, pady=2)

        # ---- 第 2 行：模型接入点（v4.0 新增，支持任意 OpenAI 兼容服务）----
        ttk.Label(cfg_frame, text="供应商:", width=10).grid(row=1, column=0, sticky=W, pady=2)
        self.var_provider = StringVar(value=self.config.get('provider', 'deepseek'))
        self.combo_provider = ttk.Combobox(
            cfg_frame, textvariable=self.var_provider,
            values=[f"{key} — {val['label']}" for key, val in PROVIDER_PRESETS.items()],
            state='readonly', width=38, font=("微软雅黑", 9))
        self.combo_provider.grid(row=1, column=1, sticky=EW, pady=2, padx=5)
        self.combo_provider.bind('<<ComboboxSelected>>', self.on_provider_change)

        ttk.Label(cfg_frame, text="接入点:", width=9).grid(row=1, column=4, sticky=W, pady=2, padx=(10, 0))
        self.var_base_url = StringVar(value=self.config.get('base_url', PROVIDER_PRESETS['deepseek']['base_url']))
        self.entry_base_url = ttk.Entry(cfg_frame, textvariable=self.var_base_url, width=25, font=("微软雅黑", 9))
        self.entry_base_url.grid(row=1, column=5, sticky=EW, pady=2, padx=5)

        # ---- 第 3 行：动作按钮 + 记住配置 ----
        btn_row = ttk.Frame(cfg_frame)
        btn_row.grid(row=2, column=0, columnspan=7, sticky=EW, pady=(4, 0))

        ttk.Button(btn_row, text="🔄 探测模型", width=12, command=self.refresh_models).pack(side=LEFT)
        ttk.Button(btn_row, text="🔌 测试 API", width=12, command=self.test_api).pack(side=LEFT, padx=(6, 0))

        self.lbl_api_state = ttk.Label(btn_row, text="模型接口: 未检测", foreground="#888",
                                       font=("微软雅黑", 9))
        self.lbl_api_state.pack(side=LEFT, padx=(10, 0))

        self.var_remember = BooleanVar(value=self.config.get('remember', True))
        ttk.Checkbutton(btn_row, text="记住配置", variable=self.var_remember).pack(side=RIGHT)

        cfg_frame.columnconfigure(1, weight=1)
        cfg_frame.columnconfigure(5, weight=1)

        # ========== 标签页 ==========
        self.notebook = ttk.Notebook(main_frame)
        self.notebook.pack(fill=BOTH, expand=True, pady=(5, 0))

        # ----- Tab 1: 任务控制 -----
        self.tab_task = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_task, text="🎯 任务控制")
        self.create_task_tab()

        # ----- Tab 2: 题目浏览 -----
        self.tab_browse = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_browse, text="📚 题目浏览")
        self.create_browse_tab()

        # ----- Tab 3: 竞赛模式 -----
        self.tab_contest = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_contest, text="🏆 竞赛")
        self.create_contest_tab()

        # ========== 状态栏 ==========
        self.statusbar = ttk.Label(self.root, text="就绪 | EOJ 自动刷题系统 — Designed by HMS_Victorious",
                                   relief=SUNKEN, anchor=W, padding=(5, 2))
        self.statusbar.pack(side=BOTTOM, fill=X)

    # ----------------------------------------------------------
    # Tab 1: 任务控制
    # ----------------------------------------------------------

    def create_task_tab(self):
        tab = self.tab_task

        # ===== 模式选择 =====
        mode_frame = ttk.LabelFrame(tab, text="🎯 模式选择", padding="8")
        mode_frame.pack(fill=X, pady=(0, 5))

        self.var_mode = StringVar(value="single")
        ttk.Radiobutton(mode_frame, text="单题模式", variable=self.var_mode,
                       value="single", command=self.on_mode_change).pack(side=LEFT, padx=(0, 15))
        ttk.Radiobutton(mode_frame, text="范围模式", variable=self.var_mode,
                       value="range", command=self.on_mode_change).pack(side=LEFT, padx=(0, 15))
        ttk.Radiobutton(mode_frame, text="归档已有题目", variable=self.var_mode,
                       value="archive", command=self.on_mode_change).pack(side=LEFT)

        param_frame = ttk.Frame(mode_frame)
        param_frame.pack(side=RIGHT)

        self.single_frame = ttk.Frame(param_frame)
        self.single_frame.pack(side=LEFT)
        ttk.Label(self.single_frame, text="题号:").pack(side=LEFT)
        self.entry_problem = ttk.Entry(self.single_frame, width=10, font=("微软雅黑", 10))
        self.entry_problem.pack(side=LEFT, padx=5)
        self.entry_problem.insert(0, "1001")

        self.range_frame = ttk.Frame(param_frame)
        ttk.Label(self.range_frame, text="从").pack(side=LEFT)
        self.entry_range_start = ttk.Entry(self.range_frame, width=7, font=("微软雅黑", 10))
        self.entry_range_start.pack(side=LEFT, padx=3)
        self.entry_range_start.insert(0, "1001")
        ttk.Label(self.range_frame, text="到").pack(side=LEFT)
        self.entry_range_end = ttk.Entry(self.range_frame, width=7, font=("微软雅黑", 10))
        self.entry_range_end.pack(side=LEFT, padx=3)
        self.entry_range_end.insert(0, "1020")

        self.archive_info = ttk.Label(mode_frame, text="", foreground="#666")
        self.archive_info.pack(side=RIGHT, padx=(15, 0))
        self.on_mode_change()

        # ===== 选项 =====
        opt_frame = ttk.LabelFrame(tab, text="⚙️ 选项", padding="8")
        opt_frame.pack(fill=X, pady=(0, 5))

        self.var_compile = BooleanVar(value=True)
        self.var_analysis = BooleanVar(value=True)
        self.var_submit = BooleanVar(value=True)

        ttk.Checkbutton(opt_frame, text="本地编译测试", variable=self.var_compile).pack(side=LEFT, padx=(0, 10))
        ttk.Checkbutton(opt_frame, text="生成刷题笔记", variable=self.var_analysis).pack(side=LEFT, padx=(0, 10))
        ttk.Checkbutton(opt_frame, text="提交到EOJ", variable=self.var_submit).pack(side=LEFT, padx=(0, 10))

        # 模型选择
        model_frame = ttk.Frame(opt_frame)
        model_frame.pack(side=LEFT, padx=(10, 0))
        ttk.Label(model_frame, text="🤖 AI 模型:").pack(side=LEFT, padx=(0, 5))
        configured_model = self.config.get('model', DEFAULT_MODELS[0])
        self.var_model = StringVar(value=configured_model)
        initial_models = list(DEFAULT_MODELS)
        if configured_model and configured_model not in initial_models:
            initial_models.insert(0, configured_model)
        # state 不设为 readonly，允许手输自定义模型名（自建/中转端点常用）
        self.combo_model = ttk.Combobox(model_frame, textvariable=self.var_model,
                                        values=initial_models, width=22)
        self.combo_model.pack(side=LEFT)

        # 超时设置
        timeout_frame = ttk.Frame(opt_frame)
        timeout_frame.pack(side=LEFT, padx=(10, 0))
        ttk.Label(timeout_frame, text="⏱ 单题超时:").pack(side=LEFT, padx=(0, 5))
        self.var_timeout = IntVar(value=self.config.get('timeout', 0))
        self.spin_timeout = ttk.Spinbox(timeout_frame, from_=0, to=600,
                                         textvariable=self.var_timeout, width=6,
                                         font=("微软雅黑", 10))
        self.spin_timeout.pack(side=LEFT)
        ttk.Label(timeout_frame, text="秒  (0=不限时)", foreground="#888",
                 font=("微软雅黑", 9)).pack(side=LEFT, padx=(3, 0))

        # ===== 操作按钮 =====
        btn_frame = ttk.Frame(tab)
        btn_frame.pack(fill=X, pady=(0, 5))

        self.btn_start = ttk.Button(btn_frame, text="🚀 开始解题", command=self.start_task, width=14)
        self.btn_start.pack(side=LEFT, padx=(0, 5))

        self.btn_stop = ttk.Button(btn_frame, text="⏹ 停止", command=self.stop_task, width=8, state=DISABLED)
        self.btn_stop.pack(side=LEFT, padx=(0, 5))

        self.btn_open = ttk.Button(btn_frame, text="📂 打开存档", command=self.open_archive, width=10)
        self.btn_open.pack(side=LEFT, padx=(0, 5))

        self.btn_test = ttk.Button(btn_frame, text="🔄 测试登录", command=self.test_login, width=10)
        self.btn_test.pack(side=LEFT)

        # ===== 进度条 =====
        progress_frame = ttk.Frame(tab)
        progress_frame.pack(fill=X, pady=(0, 5))
        self.progress = ttk.Progressbar(progress_frame, mode='determinate')
        self.progress.pack(side=LEFT, fill=X, expand=True)
        self.lbl_progress = ttk.Label(progress_frame, text="0 / 0 (0%)", width=18)
        self.lbl_progress.pack(side=LEFT, padx=(8, 0))

        # ===== 日志 =====
        log_frame = ttk.LabelFrame(tab, text="📊 运行日志", padding="5")
        log_frame.pack(fill=BOTH, expand=True)

        log_toolbar = ttk.Frame(log_frame)
        log_toolbar.pack(fill=X, pady=(0, 3))

        ttk.Button(log_toolbar, text="清空日志", command=self.clear_log, width=10).pack(side=LEFT)
        ttk.Button(log_toolbar, text="复制全部", command=self.copy_log, width=10).pack(side=LEFT, padx=5)

        # 日志级别切换
        self.btn_log_level = ttk.Button(log_toolbar, text="📋 简洁",
                                        command=self.toggle_log_level, width=8)
        self.btn_log_level.pack(side=LEFT, padx=(5, 0))

        self.lbl_task_count = ttk.Label(log_toolbar, text="", foreground="#666")
        self.lbl_task_count.pack(side=RIGHT)

        text_frame = ttk.Frame(log_frame)
        text_frame.pack(fill=BOTH, expand=True)

        self.log_text = Text(text_frame, wrap=WORD, font=("Consolas", 10),
                            bg="#1e1e1e", fg="#d4d4d4", insertbackground="white",
                            relief=SUNKEN, borderwidth=1)
        self.log_text.pack(side=LEFT, fill=BOTH, expand=True)

        scrollbar = ttk.Scrollbar(text_frame, orient=VERTICAL, command=self.log_text.yview)
        scrollbar.pack(side=RIGHT, fill=Y)
        self.log_text.configure(yscrollcommand=scrollbar.set)

        self.log_text.tag_configure("ok", foreground="#4ec9b0")
        self.log_text.tag_configure("fail", foreground="#f44747")
        self.log_text.tag_configure("warn", foreground="#dcdcaa")
        self.log_text.tag_configure("info", foreground="#9cdcfe")
        self.log_text.tag_configure("title", foreground="#c586c0", font=("Consolas", 10, "bold"))
        self.log_text.tag_configure("time", foreground="#808080")

        # 设置日志重定向
        self.redirector = TextRedirector(self.log_text, self.msg_queue)

        # v4.0：把引擎的统一日志出口接到同一个队列。
        # 旧版完全依赖 sys.stdout 重定向，多线程同时 print 会互相覆盖；
        # 现在引擎的 log_line() 直接投递到队列，不经过 stdout。
        engine.set_log_sink(self._enqueue_log)
        # 同时保留 stdout 重定向，兼容第三方库直接 print 的输出

        # ===== 本地存档列表 =====
        list_frame = ttk.LabelFrame(tab, text="📚 本地存档", padding="5")
        list_frame.pack(fill=X, pady=(5, 0))

        list_toolbar = ttk.Frame(list_frame)
        list_toolbar.pack(fill=X, pady=(0, 3))
        ttk.Button(list_toolbar, text="🔄 刷新", command=self.refresh_problem_list, width=10).pack(side=LEFT)

        columns = ('id', 'title', 'status')
        self.tree = ttk.Treeview(list_frame, columns=columns, show='headings',
                                height=4, selectmode='browse')
        self.tree.heading('id', text='题号')
        self.tree.heading('title', text='题目')
        self.tree.heading('status', text='状态')
        self.tree.column('id', width=60, anchor=CENTER)
        self.tree.column('title', width=200)
        self.tree.column('status', width=100, anchor=CENTER)

        tree_scroll = ttk.Scrollbar(list_frame, orient=VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll.set)
        self.tree.pack(side=LEFT, fill=X, expand=True)
        tree_scroll.pack(side=RIGHT, fill=Y)

        self.tree.bind('<Double-1>', self.on_tree_double_click)
        self.refresh_problem_list()

    # ----------------------------------------------------------
    # Tab 2: 题目浏览
    # ----------------------------------------------------------

    def create_browse_tab(self):
        tab = self.tab_browse

        # ===== 工具栏 =====
        toolbar = ttk.Frame(tab)
        toolbar.pack(fill=X, pady=(0, 5))

        # 登录状态（仅显示，登录需在任务控制页完成）
        self.browse_login_status = ttk.Label(toolbar, text="❌ 未登录", foreground="#f44747")
        self.browse_login_status.pack(side=LEFT, padx=(0, 10))

        self.btn_fetch_list = ttk.Button(toolbar, text="📥 刷新题目列表",
                                        command=self.fetch_problem_list, width=14, state=NORMAL)

        self.btn_fetch_list.pack(side=LEFT, padx=(0, 5))

        # 搜索筛选
        ttk.Label(toolbar, text="搜索:").pack(side=LEFT, padx=(10, 3))
        self.entry_search = ttk.Entry(toolbar, width=20, font=("微软雅黑", 9))
        self.entry_search.pack(side=LEFT, padx=(0, 5))
        self.entry_search.bind('<KeyRelease>', self.on_search_change)

        # 筛选
        self.var_filter = StringVar(value="all")
        ttk.Combobox(toolbar, textvariable=self.var_filter,
                    values=["全部", "已选", "未选", "本地已有"],
                    state="readonly", width=10).pack(side=LEFT, padx=(0, 5))
        self.var_filter.trace('w', lambda *a: self.refresh_browse_list())

        # ===== 题目表格（带复选框） =====
        list_frame = ttk.Frame(tab)
        list_frame.pack(fill=BOTH, expand=True)

        columns = ('select', 'id', 'title', 'solved')
        self.browse_tree = ttk.Treeview(list_frame, columns=columns, show='headings',
                                       height=16, selectmode='extended')
        self.browse_tree.heading('select', text='☐')
        self.browse_tree.heading('id', text='题号')
        self.browse_tree.heading('title', text='题目名称')
        self.browse_tree.heading('solved', text='解出人数')

        self.browse_tree.column('select', width=35, anchor=CENTER)
        self.browse_tree.column('id', width=70, anchor=CENTER)
        self.browse_tree.column('title', width=400)
        self.browse_tree.column('solved', width=100, anchor=CENTER)

        # 点击复选框切换选中状态
        self.browse_tree.bind('<Button-1>', self.on_browse_click)
        # 双击打开题目页面
        self.browse_tree.bind('<Double-1>', self.on_browse_double_click)

        tree_scroll = ttk.Scrollbar(list_frame, orient=VERTICAL, command=self.browse_tree.yview)
        self.browse_tree.configure(yscrollcommand=tree_scroll.set)
        self.browse_tree.pack(side=LEFT, fill=BOTH, expand=True)
        tree_scroll.pack(side=RIGHT, fill=Y)

        # 行标签
        self.browse_tree.tag_configure("selected", background="#1a3a1a")
        self.browse_tree.tag_configure("local", foreground="#4ec9b0")
        self.browse_tree.tag_configure("local_selected", background="#1a3a1a", foreground="#4ec9b0")
        
        # ★ 判题状态颜色标记
        self.browse_tree.tag_configure("verdict_ac",     foreground="#00ff00", font=("微软雅黑", 9, "bold"))
        self.browse_tree.tag_configure("verdict_tle",    foreground="#ffff00", font=("微软雅黑", 9, "bold"))
        self.browse_tree.tag_configure("verdict_wa",     foreground="#ff4444", font=("微软雅黑", 9, "bold"))
        self.browse_tree.tag_configure("verdict_pending", foreground="#888888", font=("微软雅黑", 9))
        self.browse_tree.tag_configure("verdict_none",   foreground="", font=("微软雅黑", 9))
        
        # 缓存判题结果（避免频繁请求）
        self.verdict_cache = {}  # {pid: 'AC'|'WA'|'TLE'|etc|None}
        self.verdict_cache_time = {}  # {pid: timestamp}

        # ===== 底部操作栏 =====
        bottom_frame = ttk.Frame(tab)
        bottom_frame.pack(fill=X, pady=(5, 0))

        self.lbl_browse_info = ttk.Label(bottom_frame, text="总题数: 0 | 已选: 0 | 本地已有: 0")
        self.lbl_browse_info.pack(side=LEFT)

        self.btn_select_all = ttk.Button(bottom_frame, text="全选", command=self.select_all, width=6)
        self.btn_select_all.pack(side=LEFT, padx=(15, 3))

        self.btn_deselect_all = ttk.Button(bottom_frame, text="取消全选", command=self.deselect_all, width=8)
        self.btn_deselect_all.pack(side=LEFT, padx=3)

        self.btn_select_local = ttk.Button(bottom_frame, text="选本地已有", command=self.select_local, width=10)
        self.btn_select_local.pack(side=LEFT, padx=3)

        self.btn_solve_selected = ttk.Button(bottom_frame, text="🚀 刷选中的题",
                                            command=self.solve_selected, width=14)
        self.btn_solve_selected.pack(side=RIGHT, padx=(0, 5))

        self.btn_add_to_selected = ttk.Button(bottom_frame, text="➕ 添加选中项到任务",
                                             command=self.add_selected_to_task, width=16)
        self.btn_add_to_selected.pack(side=RIGHT, padx=5)

    # ----------------------------------------------------------
    # Tab 3: 竞赛模式
    # ----------------------------------------------------------

    def create_contest_tab(self):
        tab = self.tab_contest

        # ===== 竞赛设置 =====
        setup_frame = ttk.LabelFrame(tab, text="🏆 竞赛设置", padding="8")
        setup_frame.pack(fill=X, pady=(0, 5))

        # 第一行：竞赛ID + 登录/刷新
        row1 = ttk.Frame(setup_frame)
        row1.pack(fill=X, pady=2)

        ttk.Label(row1, text="竞赛 ID:").pack(side=LEFT)
        self.entry_contest_id = ttk.Entry(row1, width=10, font=("微软雅黑", 10))
        self.entry_contest_id.pack(side=LEFT, padx=5)
        self.entry_contest_id.insert(0, "867")

        # 登录状态（仅显示，登录需要在浏览页完成）
        self.contest_login_status = ttk.Label(row1, text="❌ 未登录", foreground="#f44747")
        self.contest_login_status.pack(side=LEFT, padx=(10, 5))

        self.btn_fetch_contest = ttk.Button(row1, text="📥 获取竞赛题目",
                                           command=self.fetch_contest_problems, width=14)
        self.btn_fetch_contest.pack(side=LEFT, padx=5)

        # ===== 竞赛题目列表 =====
        list_frame = ttk.LabelFrame(tab, text="📋 竞赛题目列表", padding="5")
        list_frame.pack(fill=BOTH, expand=True)

        # 显示竞赛信息
        self.lbl_contest_info = ttk.Label(list_frame, text="输入竞赛ID后点击「获取竞赛题目」",
                                         foreground="#888")
        self.lbl_contest_info.pack(fill=X, pady=(0, 3))

        columns = ('select', 'id', 'title', 'status')
        self.contest_tree = ttk.Treeview(list_frame, columns=columns, show='headings',
                                        height=10, selectmode='extended')
        self.contest_tree.heading('select', text='☐')
        self.contest_tree.heading('id', text='题号')
        self.contest_tree.heading('title', text='题目名称')
        self.contest_tree.heading('status', text='判题状态')

        self.contest_tree.column('select', width=35, anchor=CENTER)
        self.contest_tree.column('id', width=70, anchor=CENTER)
        self.contest_tree.column('title', width=420)
        self.contest_tree.column('status', width=100, anchor=CENTER)

        # 点击切换选中状态
        self.contest_tree.bind('<Button-1>', self.on_contest_click)
        # 双击打开
        self.contest_tree.bind('<Double-1>', self.on_contest_double_click)

        tree_scroll = ttk.Scrollbar(list_frame, orient=VERTICAL, command=self.contest_tree.yview)
        self.contest_tree.configure(yscrollcommand=tree_scroll.set)
        self.contest_tree.pack(side=LEFT, fill=BOTH, expand=True)
        tree_scroll.pack(side=RIGHT, fill=Y)

        self.contest_tree.tag_configure("selected", background="#1a3a1a")
        self.contest_tree.tag_configure("verdict_ac",     foreground="#00ff00", font=("微软雅黑", 9, "bold"))
        self.contest_tree.tag_configure("verdict_tle",    foreground="#ffff00", font=("微软雅黑", 9, "bold"))
        self.contest_tree.tag_configure("verdict_wa",     foreground="#ff4444", font=("微软雅黑", 9, "bold"))
        self.contest_tree.tag_configure("verdict_none",   foreground="", font=("微软雅黑", 9))

        # ===== 底部操作 =====
        bottom_frame = ttk.Frame(tab)
        bottom_frame.pack(fill=X, pady=(5, 0))

        self.lbl_contest_bottom = ttk.Label(bottom_frame, text="共 0 题 | 已选 0 题")
        self.lbl_contest_bottom.pack(side=LEFT)

        self.btn_contest_all = ttk.Button(bottom_frame, text="全选", command=self.contest_select_all, width=6)
        self.btn_contest_all.pack(side=LEFT, padx=(15, 3))

        self.btn_contest_none = ttk.Button(bottom_frame, text="取消全选", command=self.contest_deselect_all, width=8)
        self.btn_contest_none.pack(side=LEFT, padx=3)

        self.btn_contest_start = ttk.Button(bottom_frame, text="🚀 刷该竞赛选中题",
                                           command=self.start_contest_task, width=16)
        self.btn_contest_start.pack(side=RIGHT, padx=(0, 5))

    # ----------------------------------------------------------
    # 竞赛功能
    # ----------------------------------------------------------

    def fetch_contest_problems(self):
        """获取竞赛题目列表（带 loading 反馈）"""
        if not self.eoj_client or not self.eoj_client.logged_in:
            messagebox.showwarning("提示", "请先登录")
            return

        cid = self.entry_contest_id.get().strip()
        if not cid.isdigit():
            messagebox.showerror("错误", "请输入有效的竞赛ID")
            return

        self.contest_id = cid

        # 禁用按钮，显示「加载中…」
        self.btn_fetch_contest.config(state=DISABLED, text="⏳ 加载中…")
        self.lbl_contest_info.config(text="正在获取竞赛题目，请稍候…")

        def task():
            old = sys.stdout
            sys.stdout = self.redirector
            try:
                print(f"[..] ========== 获取竞赛 {cid} 题目列表 ==========")
                problems = self.eoj_client.fetch_contest_problems(cid)
                self.contest_problems = problems
                self.selected_contest_problems.clear()
                self.root.after(0, self.refresh_contest_list)
                if problems:
                    print(f"[OK] 竞赛 {cid} 共 {len(problems)} 道题")
                else:
                    print(f"[FAIL] 无法获取竞赛 {cid} 的题目列表")
            except Exception as e:
                print(f"[FAIL] 获取竞赛题目失败: {e}")
                import traceback
                traceback.print_exc()
            finally:
                sys.stdout = old
                self.root.after(0, lambda: self.btn_fetch_contest.config(
                    state=NORMAL, text="📥 获取竞赛题目"))

        threading.Thread(target=task, daemon=True).start()

    def refresh_contest_list(self):
        """刷新竞赛题目列表（带判题状态 + 颜色）"""
        for item in self.contest_tree.get_children():
            self.contest_tree.delete(item)

        shown = 0
        for p in self.contest_problems:
            pid = p['id']
            title = p.get('title', '')
            is_selected = pid in self.selected_contest_problems
            checkbox = "☑" if is_selected else "☐"

            # 判题状态
            ckey = f"{self.contest_id}:{pid}"
            verdict = self.contest_verdict_cache.get(ckey)
            if verdict == 'AC':
                status_text = "✅ AC"
                vtag = 'verdict_ac'
            elif verdict == 'TLE':
                status_text = "⏱ TLE"
                vtag = 'verdict_tle'
            elif verdict in ('WA', 'RE', 'CE', 'MLE'):
                status_text = f"❌ {verdict}"
                vtag = 'verdict_wa'
            elif verdict == 'UNKNOWN':
                status_text = "❓ 未知"
                vtag = 'verdict_none'
            else:
                status_text = ""
                vtag = 'verdict_none'

            values = (checkbox, pid, title[:60], status_text)
            tags = []
            if is_selected:
                tags.append('selected')
            tags.append(vtag)
            self.contest_tree.insert('', END, values=values, tags=tuple(tags))
            shown += 1

        self.lbl_contest_info.config(
            text=f"竞赛 {self.contest_id}: 共 {shown} 道题"
        )
        self.lbl_contest_bottom.config(
            text=f"共 {shown} 题 | 已选 {len(self.selected_contest_problems)} 题"
        )

    def on_contest_click(self, event):
        """点击竞赛列表"""
        region = self.contest_tree.identify_region(event.x, event.y)
        if region == 'heading':
            col = self.contest_tree.identify_column(event.x)
            if col == '#1':
                if self.selected_contest_problems:
                    self.contest_deselect_all()
                else:
                    self.contest_select_all()
            return

        item = self.contest_tree.identify_row(event.y)
        if not item:
            return

        values = self.contest_tree.item(item, 'values')
        if not values:
            return

        pid = values[1]
        if pid in self.selected_contest_problems:
            self.selected_contest_problems.discard(pid)
        else:
            self.selected_contest_problems.add(pid)

        self.refresh_contest_list()

    def on_contest_double_click(self, event):
        """双击竞赛题目 → 浏览器打开"""
        item = self.contest_tree.identify_row(event.y)
        if not item:
            return
        values = self.contest_tree.item(item, 'values')
        if not values:
            return
        pid = values[1]
        url = f"https://acm.ecnu.edu.cn/contest/{self.contest_id}/problem/{pid}/"
        try:
            import webbrowser
            webbrowser.open(url)
        except:
            pass

    def contest_select_all(self):
        for p in self.contest_problems:
            self.selected_contest_problems.add(p['id'])
        self.refresh_contest_list()

    def contest_deselect_all(self):
        self.selected_contest_problems.clear()
        self.refresh_contest_list()

    def start_contest_task(self):
        """刷竞赛选中的题目"""
        if self.running:
            messagebox.showwarning("提示", "任务已在运行中")
            return

        if not self.selected_contest_problems:
            messagebox.showwarning("提示", "请先勾选要刷的竞赛题目")
            return

        if not self.contest_id:
            messagebox.showwarning("提示", "请先获取竞赛题目")
            return

        problems = sorted(self.selected_contest_problems, key=lambda x: (len(x), x))
        cid = self.contest_id
        count = len(problems)

        if not messagebox.askyesno("确认", f"确定要刷竞赛 {cid} 的 {count} 道题吗？\n"
                                          f"题目: {', '.join(problems)}"):
            return

        self.running = True
        self.stop_flag = False

        engine.EOJ_USERNAME = self.entry_username.get().strip()
        engine.EOJ_PASSWORD = self.entry_password.get().strip()
        engine.DEEPSEEK_API_KEY = self.entry_apikey.get().strip()
        engine.DEEPSEEK_MODEL = self.var_model.get()

        do_compile = self.var_compile.get()
        do_analysis = self.var_analysis.get()
        do_submit = True  # 竞赛模式默认提交

        self.btn_start.config(state=DISABLED)
        self.btn_stop.config(state=NORMAL)
        self.lbl_status.config(text="状态: 竞赛刷题中", fg="#e67e22")

        self.progress['value'] = 0
        self.lbl_progress.config(text="0 / 0 (0%)")

        print(f"[..] ========== 竞赛刷题启动 ==========")
        print(f"[..] 竞赛: Contest {cid}")
        print(f"[..] 题目: {', '.join(problems)} ({count}题)")
        timeout = self.var_timeout.get()
        print(f"[..] 选项: {'编译 ' if do_compile else ''}{'笔记 ' if do_analysis else ''}提交" +
              (f"{'超时 ' if timeout else ''}{f'{timeout}s' if timeout else ''}"))

        # 切换到任务标签页
        self.notebook.select(0)

        threading.Thread(target=self._run_task,
                        args=(problems, False, do_compile, do_analysis, True, cid, timeout),
                        daemon=True).start()

    # ----------------------------------------------------------
    # 题目浏览功能
    # ----------------------------------------------------------

    def fetch_problem_list(self):

        """获取题目列表"""
        if not self.eoj_client or not self.eoj_client.logged_in:
            messagebox.showwarning("提示", "请先登录")
            return

        def task():
            old = sys.stdout
            sys.stdout = self.redirector
            try:
                print(f"[..] ========== 获取题目列表 ==========")
                problems = self.eoj_client.fetch_all_problem_ids(max_pages=50)
                self.problem_cache = problems

                # 标记本地已有的题目
                local_ids = set(engine.list_existing_cpp_problems())
                solved_dir = self.config.get('solutions_dir', engine.DEFAULT_SOLUTIONS_DIR)
                if os.path.exists(os.path.join(solved_dir, 'index.md')):
                    with open(os.path.join(solved_dir, 'index.md'), 'r', encoding='utf-8') as f:
                        for line in f:
                            m = re.match(r'\|\s*(\d+)\s*\|', line)
                            if m:
                                local_ids.add(m.group(1))

                self.local_problem_ids = local_ids
                self.root.after(0, self.refresh_browse_list)
                print(f"[OK] 获取完成，共 {len(problems)} 道题，本地已有 {len(local_ids)} 道")
            except Exception as e:
                print(f"[FAIL] 获取失败: {e}")
                import traceback
                traceback.print_exc()
            finally:
                sys.stdout = old

        threading.Thread(target=task, daemon=True).start()

    def refresh_browse_list(self):
        """刷新浏览列表显示（带判题状态颜色）"""
        for item in self.browse_tree.get_children():
            self.browse_tree.delete(item)

        filter_mode = self.var_filter.get()
        search_text = self.entry_search.get().strip().lower()

        # ★ 批量查状态（只查本地已有的，缓存 60 秒）
        if self.problem_cache:
            local_set = getattr(self, 'local_problem_ids', set())
            need_check = [pid for pid in local_set 
                          if pid not in self.verdict_cache_time 
                          or time.time() - self.verdict_cache_time.get(pid, 0) > 60]
            if need_check and self.eoj_client and self.eoj_client.logged_in:
                threading.Thread(target=self._fetch_verdicts, args=(need_check[:50],), daemon=True).start()

        shown = 0
        for p in self.problem_cache:
            pid = p['id']
            title = p.get('title', '')
            solved = p.get('solved_count', '')

            # 搜索过滤
            if search_text and search_text not in pid and search_text not in title.lower():
                continue

            # 筛选模式
            is_selected = pid in self.selected_problems
            is_local = pid in getattr(self, 'local_problem_ids', set())

            if filter_mode == "已选" and not is_selected:
                continue
            if filter_mode == "未选" and is_selected:
                continue
            if filter_mode == "本地已有" and not is_local:
                continue

            # 确定显示标记
            checkbox = "☑" if is_selected else "☐"
            values = (checkbox, pid, title[:50], solved)

            # ★ 判题状态颜色
            verdict = self.verdict_cache.get(pid)
            if verdict == 'AC':
                vtag = 'verdict_ac'
            elif verdict == 'TLE':
                vtag = 'verdict_tle'
            elif verdict in ('WA', 'RE', 'CE', 'MLE'):
                vtag = 'verdict_wa'
            elif verdict == 'PENDING':
                vtag = 'verdict_pending'
            else:
                vtag = 'verdict_none'

            tags = []
            if is_selected:
                tags.append('selected')
            if is_local and is_selected:
                tags.append('local_selected')
            elif is_local:
                tags.append('local')
            tags.append(vtag)

            self.browse_tree.insert('', END, values=values, tags=tuple(tags))
            shown += 1

        local_count = len(getattr(self, 'local_problem_ids', set()))
        self.lbl_browse_info.config(
            text=f"总题数: {len(self.problem_cache)} | 显示: {shown} | 已选: {len(self.selected_problems)} | 本地已有: {local_count}")

    def on_search_change(self, event=None):
        self.refresh_browse_list()

    def _fetch_verdicts(self, pids):
        """批量查判题状态（有缓存 60 秒）"""
        if not self.eoj_client or not self.eoj_client.logged_in:
            return
        now = time.time()
        for pid in pids:
            if pid in self.verdict_cache_time and now - self.verdict_cache_time[pid] < 60:
                continue
            try:
                result = self.eoj_client.check_status_once(pid)
                self.verdict_cache[pid] = result
                self.verdict_cache_time[pid] = now
            except:
                pass
            time.sleep(0.3)

    def on_browse_click(self, event):
        """点击浏览列表的行或复选框"""
        region = self.browse_tree.identify_region(event.x, event.y)
        if region == 'heading':
            col = self.browse_tree.identify_column(event.x)
            if col == '#1':  # 点击表头 ☐ 列 → 全选/取消全选
                if self.selected_problems:
                    self.deselect_all()
                else:
                    self.select_all()
            return

        item = self.browse_tree.identify_row(event.y)
        if not item:
            return

        values = self.browse_tree.item(item, 'values')
        if not values:
            return

        pid = values[1]
        # 切换选中状态
        if pid in self.selected_problems:
            self.selected_problems.discard(pid)
        else:
            self.selected_problems.add(pid)

        self.refresh_browse_list()

    def on_browse_double_click(self, event):
        """双击浏览列表 → 在浏览器打开"""
        item = self.browse_tree.identify_row(event.y)
        if not item:
            return
        values = self.browse_tree.item(item, 'values')
        if not values:
            return
        pid = values[1]
        url = f"https://acm.ecnu.edu.cn/problem/{pid}/"
        try:
            import webbrowser
            webbrowser.open(url)
        except:
            pass

    def select_all(self):
        for p in self.problem_cache:
            self.selected_problems.add(p['id'])
        self.refresh_browse_list()

    def deselect_all(self):
        self.selected_problems.clear()
        self.refresh_browse_list()

    def select_local(self):
        local = getattr(self, 'local_problem_ids', set())
        for p in self.problem_cache:
            if p['id'] in local:
                self.selected_problems.add(p['id'])
        self.refresh_browse_list()

    def solve_selected(self):
        """刷选中的题"""
        if not self.selected_problems:
            messagebox.showwarning("提示", "请先勾选要刷的题目")
            return

        problems = sorted(self.selected_problems, key=int)
        count = len(problems)
        if not messagebox.askyesno("确认", f"确定要刷 {count} 道题吗？\n"
                                          f"范围: {problems[0]} ~ {problems[-1]}"):
            return

        # 切换到任务标签页并启动
        self.notebook.select(0)
        self.entry_problem.delete(0, END)
        self.entry_problem.insert(0, problems[0])
        self.var_mode.set("range")
        self.entry_range_start.delete(0, END)
        self.entry_range_start.insert(0, problems[0])
        self.entry_range_end.delete(0, END)
        self.entry_range_end.insert(0, problems[-1])
        self.on_mode_change()

        # 直接启动任务
        self.start_task()

    def add_selected_to_task(self):
        """将选中项添加到任务列表"""
        if not self.selected_problems:
            messagebox.showwarning("提示", "请先勾选题目")
            return
        problems = sorted(self.selected_problems, key=int)
        self.notebook.select(0)
        self.var_mode.set("range")
        self.entry_range_start.delete(0, END)
        self.entry_range_start.insert(0, problems[0])
        self.entry_range_end.delete(0, END)
        self.entry_range_end.insert(0, problems[-1])
        self.on_mode_change()
        self.set_status(f"已加载 {len(problems)} 道题到范围模式")

    # ----------------------------------------------------------
    # 事件处理
    # ----------------------------------------------------------

    def on_mode_change(self):
        mode = self.var_mode.get()
        if mode == 'single':
            self.single_frame.pack(side=LEFT)
            self.range_frame.pack_forget()
            self.archive_info.config(text="")
        elif mode == 'range':
            self.single_frame.pack_forget()
            self.range_frame.pack(side=LEFT)
            self.archive_info.config(text="")
        elif mode == 'archive':
            self.single_frame.pack_forget()
            self.range_frame.pack_forget()
            count = len(engine.list_existing_cpp_problems())
            self.archive_info.config(text=f"已发现 {count} 道已有题目")

    def toggle_api_key(self):
        """在明文/掩码之间切换 API Key 输入框。"""
        if self.entry_apikey.cget('show') == '':
            self.entry_apikey.configure(show="*")
        else:
            self.entry_apikey.configure(show="")

    # ----------------------------------------------------------
    # 模型接口（v4.0 新增）
    # ----------------------------------------------------------

    def on_provider_change(self, _event=None):
        """切换供应商预设：自动填好接入点与候选模型。"""
        key = self._provider_key(self.var_provider.get())
        preset = PROVIDER_PRESETS.get(key)
        if not preset:
            return
        if preset.get('base_url'):
            self.var_base_url.set(preset['base_url'])
        models = list(preset.get('models') or [])
        if models:
            self.combo_model.configure(values=models)
            if self.var_model.get() not in models:
                self.var_model.set(models[0])
        self.lbl_api_state.config(text=f"模型接口: 已选 {preset['label']}", foreground="#666")

    def refresh_models(self):
        """向 GET /models 探测真实可用模型，填进下拉框。"""
        if self.running:
            messagebox.showwarning("提示", "请先停止当前任务")
            return
        self.push_config_to_engine()
        self.lbl_api_state.config(text="模型接口: 探测中...", foreground="#1a73e8")

        def task():
            models = []
            try:
                client = engine.LLMClient(engine.get_settings().llm)
                models = client.list_models()
                client.close()
            except Exception as exc:
                print(f"[FAIL] 探测模型失败: {exc}")

            def apply():
                if models:
                    current = self.var_model.get()
                    self.combo_model.configure(values=models)
                    if current not in models:
                        self.var_model.set(models[0])
                    self.lbl_api_state.config(
                        text=f"模型接口: 可用 {len(models)} 个模型", foreground="#4ec9b0")
                    print(f"[OK] 可用模型: {', '.join(models)}")
                else:
                    self.lbl_api_state.config(text="模型接口: 探测失败", foreground="#e06c75")

            self.root.after(0, apply)
            self.root.after(0, lambda: self.set_status("模型探测完成"))

        threading.Thread(target=task, daemon=True).start()

    def test_api(self):
        """测试大模型接口连通性（鉴权 + 延迟 + 真实模型清单）。"""
        if self.running:
            messagebox.showwarning("提示", "请先停止当前任务")
            return
        self.push_config_to_engine()
        self.lbl_api_state.config(text="模型接口: 测试中...", foreground="#1a73e8")

        def task():
            settings = engine.get_settings()
            print("[..] ========== 测试模型接口 ==========")
            print(f"[..] 接入点: {settings.llm.base_url}")
            print(f"[..] 模型  : {settings.llm.model}")
            print(f"[..] Key   : {engine.mask_secret(settings.llm.api_key)}")
            try:
                client = engine.LLMClient(settings.llm)
                health = client.health_check()
                client.close()
            except Exception as exc:
                health = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

            def apply():
                if health.get("ok"):
                    self.lbl_api_state.config(
                        text=f"模型接口: 正常 ({health.get('latency')}s, {health.get('model')})",
                        foreground="#4ec9b0")
                    print(f"[OK] 接口连通，模型 {health.get('model')} 回复: {health.get('reply')!r}")
                    models = health.get("models") or []
                    if models:
                        self.combo_model.configure(values=models)
                        print(f"[OK] 可用模型: {', '.join(models)}")
                else:
                    self.lbl_api_state.config(
                        text=f"模型接口: 异常 - {str(health.get('error'))[:40]}",
                        foreground="#e06c75")
                    print(f"[FAIL] 接口异常: {health.get('error')}")

            self.root.after(0, apply)
            self.root.after(0, lambda: self.set_status("API 测试完成"))

        threading.Thread(target=task, daemon=True).start()

    def toggle_log_level(self):
        """切换日志级别：简洁 ↔ 详细"""
        if self.var_log_level.get() == 'simple':
            self.var_log_level.set('normal')
            self.btn_log_level.config(text="📋 详细")
        else:
            self.var_log_level.set('simple')
            self.btn_log_level.config(text="📋 简洁")

    def _is_noise_line(self, msg):
        """判断是否为噪音行（简洁模式下隐藏）"""
        # 隐藏这些完全无用的调试/中间步骤行
        noise_patterns = [
            r'^\[\.\.\] =+',           # 分隔线
            r'^\[\.\.\] 选项:',          # 选项
            r'^\[\.\.\] 模式:',          # 模式
            r'^\[\.\.\] 题目:',          # 题目列表
            r'^\[\.\.\] 单题超时:',       # 超时设置
            r'^\[\.\.\] 竞赛:',           # 竞赛信息
            r'^\[获取题目\]',             # 获取题目
            r'^\[提交\]',                 # 提交步骤
            r'^\[编译\]',                 # 编译步骤
            r'^\[测试\]',                 # 测试步骤
            r'^\[归档\]',                 # 归档步骤
            r'^\[AI\]',                   # AI 调用
            r'^\[API\]',                  # API 调用
            r'^\[信息\]',                 # 一般信息
            r'^\[缓存\]',                 # 缓存信息
            r'^\[尝试\]',                 # 重试
            r'^  \[',                     # 缩进的子步骤
            r'^       ',                  # 缩进的详细信息
            r'^  \(耗时',                  # 耗时信息
            r'^  OCR',                    # OCR 详情
            r'^  \[!\]',                  # 感叹号内部信息（保留[WARN]）
            r'^\s*$',                     # 空行
        ]
        for pattern in noise_patterns:
            if re.match(pattern, msg):
                return True
        return False

    def _simplify_msg(self, msg):
        """将完整日志消息简化为用户友好的简短格式"""
        # 登录状态
        if '[OK]' in msg and '登录成功' in msg:
            return '✅ 登录成功'
        if '[FAIL]' in msg and '登录失败' in msg:
            return '❌ 登录失败'

        # 竞赛题目获取
        m = re.match(r'\[OK\] 竞赛 (\d+) 共 (\d+) 道题', msg)
        if m:
            return f'📋 竞赛 {m.group(1)}: 共 {m.group(2)} 道题'
        if '[FAIL]' in msg and '竞赛' in msg:
            return f'❌ {msg.replace("[FAIL] ", "").strip()}'

        # 题目列表获取
        m = re.match(r'\[OK\] 获取完成，共 (\d+) 道题', msg)
        if m:
            return f'📋 共获取 {m.group(1)} 道题'
        if '[FAIL]' in msg and '获取失败' in msg:
            return '❌ 获取题目列表失败'

        # 任务完成汇总
        if '任务完成' in msg and '=' not in msg:
            m = re.search(r'成功: (\d+), 失败: (\d+)', msg)
            if m:
                s, f = m.group(1), m.group(2)
                if int(f) == 0:
                    return f'✅ 全部完成! 成功: {s}'
                else:
                    return f'⚠️ 完成! 成功: {s}, 失败: {f}'

        # 解题结果（单题）
        if '✅ 已提交' in msg or '[' in msg and '✅' in msg and '提交' in msg:
            return msg
        if '❌' in msg and ('FAIL' in msg or '失败' in msg or '异常' in msg):
            # 保留原始错误信息
            return msg

        return None  # 不简化，按原样显示

    def clear_log(self):
        self.log_text.delete(1.0, END)

    def copy_log(self):
        content = self.log_text.get(1.0, END)
        self.root.clipboard_clear()
        self.root.clipboard_append(content)
        self.statusbar.config(text="日志已复制到剪贴板")

    def open_archive(self):
        path = self.config.get('solutions_dir', engine.DEFAULT_SOLUTIONS_DIR)
        if os.path.exists(path):
            os.startfile(path)
        else:
            messagebox.showinfo("提示", f"存档目录不存在:\n{path}")

    def on_closing(self):
        if self.running:
            if not messagebox.askyesno("确认", "正在运行任务，确认退出？"):
                return
            self.stop_flag = True
        if self.var_remember.get():
            self.save_config()
        self.root.destroy()

    def set_status(self, text):
        self.statusbar.config(text=text)

    def update_log_text(self):
        try:
            # 每轮最多处理 20 条，防止大量 print 涌入导致 GUI 卡死
            for _ in range(20):
                msg = self.msg_queue.get_nowait()
                self._append_log(msg)
        except queue.Empty:
            pass
        self.root.after(100, self.update_log_text)

    def _append_log(self, msg):
        # 去除末尾换行
        msg = msg.rstrip('\n\r ')

        # 简洁模式：过滤噪音 + 尝试简化
        if self.var_log_level.get() == 'simple':
            # 尝试先简化（对于可简化的消息，用友好格式显示）
            simplified = self._simplify_msg(msg)
            if simplified:
                msg = simplified
                tag = "ok" if '✅' in msg else ("fail" if '❌' in msg else "info")
                self.log_text.insert(END, msg + '\n', tag)
                self.log_text.see(END)
                self.log_buffer.append(msg)
                return

            # 检查是否为噪音行
            if self._is_noise_line(msg):
                return  # 直接丢弃

            # 保留关键行，但美化前缀
            if msg.startswith('[OK]'):
                msg = '✅ ' + msg[4:].strip()
                tag = "ok"
            elif msg.startswith('[FAIL]'):
                msg = '❌ ' + msg[5:].strip()
                tag = "fail"
            elif msg.startswith('[WARN]'):
                msg = '⚠️ ' + msg[5:].strip()
                tag = "warn"
            else:
                tag = "info"

            self.log_text.insert(END, msg + '\n', tag)
            self.log_text.see(END)
            self.log_buffer.append(msg)
            return

        # 详细模式：完整显示所有日志（带颜色标记）
        tag = "info"
        if msg.startswith('[OK]') or msg.startswith('[v]') or '通过' in msg or '成功' in msg:
            tag = "ok"
        elif msg.startswith('[FAIL]') or msg.startswith('[NO]') or '失败' in msg or '错误' in msg:
            tag = "fail"
        elif msg.startswith('[WARN]') or msg.startswith('[!!]'):
            tag = "warn"
        elif msg.startswith('===') or msg.startswith('---'):
            tag = "title"

        self.log_text.insert(END, msg + '\n', tag)
        self.log_text.see(END)
        self.log_buffer.append(msg)

    def poll_log_queue(self):
        self.update_log_text()

    # ----------------------------------------------------------
    # 本地存档列表
    # ----------------------------------------------------------

    def refresh_problem_list(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

        solutions_dir = self.config.get('solutions_dir', engine.DEFAULT_SOLUTIONS_DIR)
        index_path = os.path.join(solutions_dir, 'index.md')

        entries = []
        if os.path.exists(index_path):
            with open(index_path, 'r', encoding='utf-8') as f:
                for line in f:
                    m = re.match(r'\|\s*(\d+)\s*\|.*?\[(.+?)\]\(.*?\)\s*\|\s*(.+?)\s*\|', line)
                    if m:
                        pid = m.group(1)
                        title = m.group(2)
                        status = m.group(3)
                        entries.append((pid, title, status))

        for pid, title, status in entries[:30]:
            self.tree.insert('', END, values=(pid, title[:30], status))

        if entries:
            self.lbl_task_count.config(text=f"已存档: {len(entries)} 题")
        else:
            self.lbl_task_count.config(text="本地存档为空")

    def on_tree_double_click(self, event):
        sel = self.tree.selection()
        if sel:
            item = self.tree.item(sel[0])
            pid = item['values'][0]
            solutions_dir = self.config.get('solutions_dir', engine.DEFAULT_SOLUTIONS_DIR)
            readme = os.path.join(solutions_dir, str(pid), 'README.md')
            if os.path.exists(readme):
                os.startfile(readme)
            else:
                folder = os.path.join(solutions_dir, str(pid))
                if os.path.exists(folder):
                    os.startfile(folder)

    # ----------------------------------------------------------
    # 测试登录
    # ----------------------------------------------------------

    def test_login(self):
        if self.running:
            messagebox.showwarning("提示", "请先停止当前任务")
            return

        self.set_status("正在测试登录...")
        self.push_config_to_engine()

        def task():
            old_stdout = sys.stdout
            sys.stdout = self.redirector
            try:
                print(f"[..] ========== 测试登录 ==========")
                client = engine.EOJClient()
                if client.login():
                    self.eoj_client = client
                    print("[OK] ✅ 登录成功！")
                    self.root.after(0, lambda: self.set_status("登录成功"))
                    self.root.after(0, lambda: self.browse_login_status.config(
                        text="✅ 已登录", foreground="#4ec9b0"))
                    # 同步更新竞赛 Tab 的登录状态
                    self.root.after(0, lambda: self.contest_login_status.config(
                        text="✅ 已登录", foreground="#4ec9b0"))

                else:
                    print("[FAIL] ❌ 登录失败！")
                    self.root.after(0, lambda: self.set_status("登录失败"))
            except Exception as e:
                print(f"[FAIL] 登录异常: {e}")
                self.root.after(0, lambda: self.set_status(f"登录异常: {e}"))
            finally:
                sys.stdout = old_stdout

        threading.Thread(target=task, daemon=True).start()

    # ----------------------------------------------------------
    # 开始/停止任务
    # ----------------------------------------------------------

    def start_task(self):
        if self.running:
            messagebox.showwarning("提示", "任务已在运行中")
            return

        self.running = True
        self.stop_flag = False

        self.push_config_to_engine()

        mode = self.var_mode.get()
        if mode == 'single':
            problem_id = self.entry_problem.get().strip()
            if not problem_id.isdigit():
                messagebox.showerror("错误", "请输入有效的题号")
                self.running = False
                return
            problems = [problem_id]
        elif mode == 'range':
            start = self.entry_range_start.get().strip()
            end = self.entry_range_end.get().strip()
            if not start.isdigit() or not end.isdigit():
                messagebox.showerror("错误", "请输入有效的范围")
                self.running = False
                return
            problems = [str(i) for i in range(int(start), int(end) + 1)]
        elif mode == 'archive':
            problems = engine.list_existing_cpp_problems()
            if not problems:
                messagebox.showinfo("提示", "未找到已有题目")
                self.running = False
                return

        do_compile = self.var_compile.get()
        do_analysis = self.var_analysis.get()
        do_submit = self.var_submit.get()

        self.btn_start.config(state=DISABLED)
        self.btn_stop.config(state=NORMAL)
        self.lbl_status.config(text="状态: 运行中", fg="#e67e22")

        self.progress['value'] = 0
        self.lbl_progress.config(text="0 / 0 (0%)")

        print(f"[..] ========== 任务启动 ==========")
        print(f"[..] 模式: {mode}")
        print(f"[..] 题目: {problems[0] if len(problems)==1 else f'{problems[0]}-{problems[-1]} ({len(problems)}题)'}")
        timeout = self.var_timeout.get()
        print(f"[..] 选项: {'编译 ' if do_compile else ''}{'笔记 ' if do_analysis else ''}{'提交 ' if do_submit else ''}" +
              (f"{'超时 ' if timeout else ''}{f'{timeout}s' if timeout else ''}"))
        if timeout:
            print(f"[..] 单题超时: {timeout}s（整题总时长上限）")

        threading.Thread(target=self._run_task,
                        args=(problems, mode == 'archive', do_compile, do_analysis, do_submit, None, timeout),
                        daemon=True).start()

    def stop_task(self):
        if self.running:
            self.stop_flag = True
            print("[WARN] ⏹ 正在停止任务...")
            self.set_status("正在停止...")

    def _run_task(self, problems, is_archive, do_compile, do_analysis, do_submit, contest_id=None, timeout=0):
        old_stdout = sys.stdout
        sys.stdout = self.redirector

        # 设置引擎超时
        if timeout:
            engine.PER_PROBLEM_TIMEOUT = timeout
            print(f"[..] 单题超时: {timeout}s（整题总时长上限）")

        try:
            # ★ 修复 Bug：根据编译选项创建 tester，而非硬编码为 None
            tester = None
            if do_compile:
                engine.find_gpp()
                if engine.GPP_PATH:
                    tester = engine.CodeTester()

            archiver = engine.SolutionArchiver(self.config.get('solutions_dir'))
            solver = engine.DeepSeekSolver()
            eoj_client = self.eoj_client if self.eoj_client and self.eoj_client.logged_in else None
            if not eoj_client and not is_archive and do_submit:
                eoj_client = engine.EOJClient()

            total = len(problems)
            success = 0
            fail = 0

            for i, pid in enumerate(problems):
                if self.stop_flag:
                    print("[WARN] ⏹ 任务已停止")
                    break

                progress_pct = int((i / total) * 100)
                self.root.after(0, lambda p=progress_pct: self.progress.configure(value=p))
                self.root.after(0, lambda i=i, t=total, p=progress_pct:
                                self.lbl_progress.configure(text=f"{i+1}/{t} ({p}%)"))
                self.root.after(0, lambda pid=pid, i=i, t=total:
                               self.set_status(f"正在处理: {pid} ({i+1}/{t})"))

                try:
                    if is_archive:
                        result = engine.archive_existing_problem(
                            pid, solver=solver, archiver=archiver, eoj_client=eoj_client
                        )
                        if result:
                            success += 1
                        else:
                            fail += 1
                    else:
                        # ★ 修复 Bug：根据用户是否勾选"本地编译测试"决定是否传入 tester
                        current_tester = tester if do_compile else None
                        result = engine.solve_single_problem(
                            pid,
                            skip_login=(eoj_client is not None and eoj_client.logged_in),
                            skip_submit=not do_submit,
                            skip_analysis=not do_analysis,
                            eoj_client=eoj_client,
                            solver=solver,
                            tester=current_tester,
                            archiver=archiver,
                            contest_id=contest_id
                        )
                        if result == 'SUCCESS':
                            success += 1
                        else:
                            fail += 1

                    # 竞赛模式：缓存判题结果
                    if contest_id:
                        ckey = f"{contest_id}:{pid}"
                        # 竞赛 status 返回 403，无法查到具体结果，先标记 UNKNOWN
                        self.contest_verdict_cache[ckey] = 'UNKNOWN'
                        self.contest_verdict_cache_time[ckey] = time.time()
                        # 刷新竞赛列表更新状态显示
                        self.root.after(0, self.refresh_contest_list)
                except Exception as e:
                    print(f"[FAIL] 解题异常 [{pid}]: {e}")
                    import traceback
                    traceback.print_exc()
                    fail += 1

                if not is_archive and len(problems) > 1:
                    time.sleep(2)

            self.root.after(0, lambda: self.progress.configure(value=100))
            self.root.after(0, lambda t=total: self.lbl_progress.configure(text=f"{t}/{t} (100%)"))

            print(f"\n[OK] ========== 任务完成 ==========")
            print(f"[OK] 成功: {success}, 失败: {fail}")

        except Exception as e:
            print(f"[FAIL] 任务异常: {e}")
            import traceback
            traceback.print_exc()
        finally:
            sys.stdout = old_stdout
            self.running = False
            self.root.after(0, self._on_task_done)

    def _on_task_done(self):
        self.btn_start.config(state=NORMAL)
        self.btn_stop.config(state=DISABLED)
        self.lbl_status.config(text="状态: 就绪", fg="#666")
        self.set_status("任务完成")
        self.refresh_problem_list()


# ============================================================
# 验证码弹窗
# ============================================================

class CaptchaDialog(Toplevel):
    def __init__(self, parent, image_data):
        super().__init__(parent)
        self.title("验证码")
        self.result = ''
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self.update_idletasks()

        frame = ttk.Frame(self, padding="15")
        frame.pack(fill=BOTH, expand=True)

        ttk.Label(frame, text="验证码自动识别失败，请手动输入：",
                 font=("微软雅黑", 10)).pack(pady=(0, 10))

        try:
            img = Image.open(io.BytesIO(image_data))
            img = img.resize((img.width * 2, img.height * 2), Image.LANCZOS)
            self.tk_img = ImageTk.PhotoImage(img)
            img_label = Label(frame, image=self.tk_img, bg="white")
            img_label.pack(pady=(0, 10))
        except Exception as e:
            ttk.Label(frame, text=f"[图片加载失败: {e}]",
                     foreground="red").pack(pady=(0, 10))

        input_frame = ttk.Frame(frame)
        input_frame.pack(fill=X)

        ttk.Label(input_frame, text="答案:").pack(side=LEFT)
        self.entry = ttk.Entry(input_frame, font=("微软雅黑", 14), width=15)
        self.entry.pack(side=LEFT, fill=X, expand=True, padx=5)
        self.entry.focus_set()

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=X, pady=(10, 0))
        ttk.Button(btn_frame, text="确定", command=self.on_ok, width=10).pack(side=RIGHT, padx=(5, 0))
        ttk.Button(btn_frame, text="取消", command=self.on_cancel, width=10).pack(side=RIGHT)

        self.bind('<Return>', lambda e: self.on_ok())
        self.bind('<Escape>', lambda e: self.on_cancel())

        self.update_idletasks()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        px = parent.winfo_x()
        py = parent.winfo_y()
        w = self.winfo_width()
        h = self.winfo_height()
        x = px + (pw - w) // 2
        y = py + (ph - h) // 2
        self.geometry(f"+{x}+{y}")

    def on_ok(self):
        self.result = self.entry.get().strip()
        if not self.result:
            messagebox.showwarning("提示", "请输入验证码答案", parent=self)
            return
        self.destroy()

    def on_cancel(self):
        self.result = ''
        self.destroy()


# ============================================================
# 启动
# ============================================================

def main():
    root = Tk()
    app = EOJGUI(root)
    root.mainloop()


if __name__ == '__main__':
    main()
