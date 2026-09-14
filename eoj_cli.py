#!/usr/bin/env python3
"""
EOJ 自动刷题系统 - 交互控制台 v1.0
====================================
一个交互式命令行程序，在它的命令行里直接输入指令即可操作。

用法:
  python eoj_cli.py          # 进入交互控制台
  python eoj_cli.py solve 1001   # 直接执行单条命令后退出
"""

import sys
import os
import time
import re
import subprocess
import shutil

# Fix console encoding for Windows (GBK -> UTF-8)
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        import io as _io
        sys.stdout = _io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    # stdin 也必须一起改：Windows 上默认是 GBK(cp936)，用管道喂命令时
    # 首行的 UTF-8 BOM（EF BB BF）会被解成「锘縟，命令名就此匹配失败。
    try:
        sys.stdin.reconfigure(encoding='utf-8-sig')
    except (AttributeError, ValueError, OSError):
        pass

# Use ASCII-safe symbols for GBK compatibility
CHECK = '[OK]'
CROSS = '[NO]'
INFO = '[..]'
WARN = '[!!]'

# ============================================================
# 确保当前目录在 path 中，以便导入 eoj_auto_solver
# ============================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# 尝试导入 colorama（用于 Windows 彩色输出，非必须）
COLORAMA_AVAILABLE = False
try:
    from colorama import init, Fore, Back, Style
    init()
    COLORAMA_AVAILABLE = True
except ImportError:
    pass

# ============================================================
# 彩色输出工具
# ============================================================

class Colors:
    """跨平台彩色输出（兼容无 colorama 环境）"""
    if COLORAMA_AVAILABLE:
        GREEN = Fore.GREEN
        RED = Fore.RED
        BLUE = Fore.CYAN
        YELLOW = Fore.YELLOW
        MAGENTA = Fore.MAGENTA
        BOLD = Style.BRIGHT
        RESET = Style.RESET_ALL
        DIM = Style.DIM
    else:
        GREEN = '\033[92m'
        RED = '\033[91m'
        BLUE = '\033[96m'
        YELLOW = '\033[93m'
        MAGENTA = '\033[95m'
        BOLD = '\033[1m'
        RESET = '\033[0m'
        DIM = '\033[2m'

def cprint(text, color='', end='\n'):
    """彩色打印"""
    print(f"{color}{text}{Colors.RESET}", end=end)

def print_banner():
    """打印启动横幅"""
    banner = f"""
{Colors.BOLD}{Colors.BLUE}╔══════════════════════════════════════════════════════╗
║          EOJ 自动刷题系统 - 交互控制台 v1.0           ║
║          华东师范大学在线评测系统                      ║
╚══════════════════════════════════════════════════════╝{Colors.RESET}
"""
    print(banner)

def print_header(text):
    """打印分隔标题"""
    width = 56
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'=' * width}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}  {text}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'=' * width}{Colors.RESET}")

def print_ok(text):
    """打印成功信息"""
    print(f"  {Colors.GREEN}[v] {text}{Colors.RESET}")

def print_fail(text):
    """打印失败信息"""
    print(f"  {Colors.RED}[x] {text}{Colors.RESET}")

def print_info(text):
    """打印提示信息"""
    print(f"  {Colors.BLUE}[i] {text}{Colors.RESET}")

def print_warn(text):
    """打印警告信息"""
    print(f"  {Colors.YELLOW}[!] {text}{Colors.RESET}")

def print_dim(text):
    """打印暗淡文字"""
    print(f"{Colors.DIM}{text}{Colors.RESET}")


# ============================================================
# 导入后端引擎
# ============================================================

def import_engine():
    """导入 eoj_auto_solver 中的核心类"""
    try:
        # 先尝试加载模块
        import importlib.util
        spec = importlib.util.spec_from_file_location("eoj_auto_solver",
            os.path.join(BASE_DIR, "eoj_auto_solver.py"))
        if spec is None:
            print_fail("无法加载 eoj_auto_solver.py")
            return None
        
        engine = importlib.util.module_from_spec(spec)
        
        # 在加载前注入所需依赖
        sys.modules['eoj_auto_solver'] = engine
        spec.loader.exec_module(engine)
        
        return engine
    except Exception as e:
        print_fail(f"导入引擎失败: {e}")
        return None


# ============================================================
# 历史命令管理器
# ============================================================

class CommandHistory:
    """简单命令历史管理器（替代 readline）"""
    
    def __init__(self, max_size=100):
        self.history = []
        self.max_size = max_size
        self.pos = 0  # 当前位置（-1 表示新输入）
        self.current_input = ''
    
    def add(self, cmd):
        cmd = cmd.strip()
        if cmd and (not self.history or self.history[-1] != cmd):
            self.history.append(cmd)
            if len(self.history) > self.max_size:
                self.history.pop(0)
        self.pos = len(self.history)
        self.current_input = ''
    
    def get_prev(self):
        if len(self.history) == 0:
            return None
        if self.pos == len(self.history):
            # 保存当前输入
            pass
        if self.pos > 0:
            self.pos -= 1
            return self.history[self.pos]
        return None
    
    def get_next(self):
        if self.pos < len(self.history) - 1:
            self.pos += 1
            return self.history[self.pos]
        elif self.pos == len(self.history) - 1:
            self.pos += 1
            return ''
        return None


# ============================================================
# 交互式控制台
# ============================================================

class EOJConsole:
    """EOJ 交互式控制台"""

    PROMPT = f"{Colors.BOLD}{Colors.GREEN}eoj>{Colors.RESET} "

    def __init__(self):
        self.engine = None
        self.eoj_client = None
        self.solver = None
        self.tester = None
        self.archiver = None
        self.gpp_found = False
        self.running = True
        self.history = CommandHistory()
        
        # 命令映射
        self.commands = {
            'solve': self.cmd_solve,
            'batch': self.cmd_batch,
            'archive': self.cmd_archive,
            'login': self.cmd_login,
            'status': self.cmd_status,
            'view': self.cmd_view,
            'solutions': self.cmd_solutions,
            'list': self.cmd_solutions,
            'stats': self.cmd_stats,
            'clear': self.cmd_clear,
            'models': self.cmd_models,
            'model': self.cmd_models,
            'doctor': self.cmd_doctor,
            'help': self.cmd_help,
            'exit': self.cmd_exit,
            'quit': self.cmd_exit,
            '': self.cmd_empty,
        }
        self.command_aliases = {
            'q': 'quit',
            'h': 'help',
            '?': 'help',
            'c': 'clear',
            'ls': 'solutions',
            'solve': 'solve',
        }

    def initialize(self):
        """初始化控制台"""
        print_banner()

        # Step 1: 检测编译环境
        print_header("系统检测")
        sys.stdout.flush()

        # 检测 g++
        self.gpp_found = self._check_gpp()

        # Step 2: 导入引擎
        print_header("加载引擎")
        sys.stdout.flush()
        self.engine = import_engine()
        if not self.engine:
            print_fail("引擎加载失败，部分功能不可用")
            return False

        # Step 3: 初始化组件
        self.eoj_client = None  # 需要时再初始化
        self.solver = self.engine.DeepSeekSolver()
        
        if self.gpp_found:
            self.tester = self.engine.CodeTester()
        
        self.archiver = self.engine.SolutionArchiver()

        # Step 4: 显示概览
        self._show_overview()

        return True

    def _check_gpp(self):
        """检测 g++ 编译器"""
        try:
            result = subprocess.run(['g++', '--version'], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                print_ok("g++ 编译器已就绪")
                return True
        except:
            pass
        
        # 尝试已知路径
        common_paths = [
            r'D:\desktop\goodbyeworld\x86_64-8.1.0-release-posix-seh-rt_v6-rev0\mingw64\bin\g++.exe',
            r'C:\MinGW\bin\g++.exe',
            r'C:\MinGW-w64\bin\g++.exe',
        ]
        for p in common_paths:
            if os.path.exists(p):
                print_ok(f"g++ 编译器已就绪 ({p})")
                return True
        
        print_warn("未检测到 g++ 编译器（将跳过编译测试）")
        return False

    def _show_overview(self):
        """显示概览信息"""
        print_header("信息概览")
        
        # EOJ 存档信息
        if self.archiver and os.path.exists(self.archiver.solutions_dir):
            solution_dirs = [d for d in os.listdir(self.archiver.solutions_dir)
                           if os.path.isdir(os.path.join(self.archiver.solutions_dir, d))
                           and d.isdigit()]
            print_ok(f"本地存档: {len(solution_dirs)} 道题")
            print_dim(f"  目录: {self.archiver.solutions_dir}")
        
        # eoj/ 目录已有代码
        eoj_dir = os.path.join(BASE_DIR, 'eoj')
        if os.path.isdir(eoj_dir):
            cpp_files = [f for f in os.listdir(eoj_dir) if f.endswith('.cpp')]
            problem_ids = set()
            for f in cpp_files:
                m = re.match(r'(\d+)', f)
                if m:
                    problem_ids.add(m.group(1))
            if problem_ids:
                print_ok(f"已有解题代码: {len(problem_ids)} 道题 (eoj/ 目录)")
        
        print()

    def _get_eoj_client(self):
        """获取或初始化 EOJ 客户端"""
        if self.eoj_client is None:
            self.eoj_client = self.engine.EOJClient()
        return self.eoj_client

    # ============================================================
    # 命令处理器
    # ============================================================

    def cmd_solve(self, args):
        """solve <题号> - 刷单题"""
        if not args:
            print_warn("用法: solve <题号>  例: solve 1001")
            return
        pid = args[0].strip()
        print_header(f"刷题: Problem {pid}")
        
        # ★ 修复：DeepSeekSolver 是一个类（始终为 truthy），
        # 导致 eoj_client 永远为 None，永远无法登录。
        # 实际应始终获取 eoj_client 实例
        eoj_client = self._get_eoj_client()
        
        # 判断是否需要登录（未登录时自动尝试）
        need_login = False
        if eoj_client and not eoj_client.logged_in:
            print_info("需要登录 EOJ...")
            if not eoj_client.login():
                print_warn("登录失败，将使用离线模式（仅生成代码，不提交）")
                eoj_client = None

        # 调用 solve_single_problem
        try:
            result = self.engine.solve_single_problem(
                pid,
                skip_login=(eoj_client is None),
                skip_submit=(eoj_client is None),
                skip_analysis=False,
                eoj_client=eoj_client,
                solver=self.solver,
                tester=self.tester,
                archiver=self.archiver
            )
            if result == 'SUCCESS':
                print_ok(f"题目 {pid} 完成！")
            elif result == 'FAIL_TEST':
                print_warn(f"题目 {pid}: 样例测试未通过")
            elif result == 'FAIL_COMPILE':
                print_fail(f"题目 {pid}: 编译失败")
            else:
                print_fail(f"题目 {pid}: 失败 ({result})")
        except KeyboardInterrupt:
            print_warn("已中断")
        except Exception as e:
            print_fail(f"异常: {e}")
            import traceback
            traceback.print_exc()

    def cmd_batch(self, args):
        """batch <范围> - 批量刷题"""
        if not args:
            print_warn("用法: batch <范围>  例: batch 1001-1020")
            return
        
        range_str = args[0].strip()
        ids = self.engine.extract_problem_ids_from_range(range_str)
        if not ids:
            print_fail("无效的范围格式，请使用如: 1001-1020")
            return
        
        print_header(f"批量刷题: {len(ids)} 道")
        print_info(f"范围: {range_str}")
        print_dim("按 Ctrl+C 可安全中断\n")
        
        eoj_client = self._get_eoj_client()
        need_login = False
        if eoj_client and not eoj_client.logged_in:
            print_info("需要登录 EOJ...")
            if not eoj_client.login():
                print_warn("登录失败，将使用离线模式")
                eoj_client = None
        
        success = 0
        fail = 0
        try:
            for i, pid in enumerate(ids, 1):
                print(f"\n{Colors.BOLD}[{i}/{len(ids)}] Problem {pid}{Colors.RESET}")
                
                result = self.engine.solve_single_problem(
                    pid,
                    skip_login=(eoj_client is None),
                    skip_submit=(eoj_client is None),
                    skip_analysis=False,
                    eoj_client=eoj_client,
                    solver=self.solver,
                    tester=self.tester,
                    archiver=self.archiver
                )
                
                if result == 'SUCCESS':
                    success += 1
                    print_ok(f"✓ {pid}")
                else:
                    fail += 1
                    print_fail(f"✗ {pid} ({result})")
                
                if i < len(ids):
                    time.sleep(2)  # 避免请求过快
                    
        except KeyboardInterrupt:
            print_warn("\n批量刷题已中断")
        
        print_header("批量结果")
        print_ok(f"成功: {success}")
        if fail:
            print_fail(f"失败: {fail}")
        print_info(f"总计: {len(ids)}")

    def cmd_archive(self, args):
        """archive <题号|范围|all> - 归档已有题目"""
        if not args:
            print_warn("用法:")
            print_warn("  archive <题号>      归档单题   例: archive 1001")
            print_warn("  archive <范围>      归档多题   例: archive 1001-1020")
            print_warn("  archive all         归档全部已有题目")
            return
        
        arg = args[0].strip().lower()
        
        problem_ids = []
        if arg == 'all':
            eoj_dir = os.path.join(BASE_DIR, 'eoj')
            problem_ids = self.engine.list_existing_cpp_problems(eoj_dir)
            if not problem_ids:
                print_fail("eoj/ 目录下未找到 .cpp 文件")
                return
            print_info(f"在 eoj/ 目录找到 {len(problem_ids)} 道题")
        elif '-' in arg:
            ids = self.engine.extract_problem_ids_from_range(arg)
            if ids:
                problem_ids = ids
            else:
                print_fail("无效的范围格式")
                return
        else:
            problem_ids = [arg]
        
        print_header(f"归档已有题目: {len(problem_ids)} 道")
        print_dim("按 Ctrl+C 可安全中断\n")
        
        eoj_client = self.engine.EOJClient()
        success = 0
        fail = 0
        
        try:
            for i, pid in enumerate(problem_ids, 1):
                print(f"\n{Colors.BOLD}[{i}/{len(problem_ids)}] Problem {pid}{Colors.RESET}")
                
                result = self.engine.archive_existing_problem(
                    pid,
                    solver=self.solver,
                    archiver=self.archiver,
                    eoj_client=eoj_client
                )
                
                if result:
                    success += 1
                    print_ok(f"✓ {pid}")
                else:
                    fail += 1
                    print_fail(f"✗ {pid}")
                
                if i < len(problem_ids):
                    time.sleep(2)
                    
        except KeyboardInterrupt:
            print_warn("\n归档已中断")
        
        print_header("归档结果")
        print_ok(f"成功: {success}")
        if fail:
            print_fail(f"失败: {fail}")

    def cmd_login(self, args):
        """login - 登录 EOJ"""
        print_header("登录 EOJ")
        client = self._get_eoj_client()
        if client.logged_in:
            print_ok("已经登录了！")
            return
        if client.login():
            print_ok("登录成功！")
        else:
            print_fail("登录失败")

    def cmd_status(self, args):
        """status - 显示当前状态"""
        print_header("系统状态")
        
        # EOJ 登录状态
        if self.eoj_client and self.eoj_client.logged_in:
            print_ok("EOJ: 已登录")
        else:
            print_warn("EOJ: 未登录")
        
        # g++ 编译器
        if self.gpp_found:
            print_ok("g++: 已就绪")
        else:
            print_warn("g++: 未找到")
        
        # 大模型接口（v4.0：显示接入点与模型，Key 打码）
        settings = self.engine.get_settings()
        if settings.llm.api_key:
            print_ok("模型接口: 已配置")
            print_info(f"  接入点: {settings.llm.base_url}")
            print_info(f"  模型  : {settings.llm.model}")
            print_info(f"  API Key: {self.engine.mask_secret(settings.llm.api_key)}")
        else:
            print_warn("模型接口: 未配置 API Key")
        
        # 存档统计
        if self.archiver:
            sol_dir = self.archiver.solutions_dir
            if os.path.exists(sol_dir):
                dirs = [d for d in os.listdir(sol_dir)
                       if os.path.isdir(os.path.join(sol_dir, d)) and d.isdigit()]
                print_ok(f"本地存档: {len(dirs)} 道题")
                print_dim(f"  路径: {sol_dir}")
            else:
                print_warn("本地存档: 目录尚未创建")
        
        # eoj/ 目录统计
        eoj_dir = os.path.join(BASE_DIR, 'eoj')
        if os.path.isdir(eoj_dir):
            problems = self.engine.list_existing_cpp_problems(eoj_dir)
            if problems:
                print_ok(f"已有代码: {len(problems)} 道题 (eoj/ 目录)")

    def cmd_models(self, args):
        """models - 探测接入点支持的模型；models <名称> 切换当前模型"""
        settings = self.engine.get_settings()
        if args:
            name = args[0].strip()
            settings.llm.model = name
            print_ok(f"当前模型已切换为: {settings.llm.model}")
            try:
                self.engine.save_gui_config({})
            except Exception as exc:
                print_warn(f"配置保存失败: {exc}")
            return

        print_header("模型探测")
        print_info(f"接入点: {settings.llm.base_url}")
        print_info(f"API Key: {self.engine.mask_secret(settings.llm.api_key)}")
        try:
            client = self.engine.LLMClient(settings.llm)
            models = client.list_models()
            client.close()
        except Exception as exc:
            print_fail(f"探测失败: {exc}")
            return
        if not models:
            print_fail("未能获取模型列表，请检查 API Key 与接入点")
            return
        for name in models:
            mark = "  <- 当前使用" if name == settings.llm.model else ""
            print(f"  {Colors.BLUE}{name}{Colors.RESET}{mark}")
        if settings.llm.model not in models:
            print_warn(f"当前模型 '{settings.llm.model}' 不在可用列表中，建议 models {models[0]}")

    def cmd_doctor(self, args):
        """doctor - 环境自检（依赖 / 编译器 / 模型接口）"""
        issues = self.engine.doctor()
        if issues:
            print_warn(f"自检完成，发现 {issues} 个问题")
        else:
            print_ok("自检完成，一切正常")

    def cmd_view(self, args):
        """view <题号> - 查看已生成的笔记/代码"""
        if not args:
            print_warn("用法: view <题号>  例: view 1001")
            return
        pid = args[0].strip()
        
        if not self.archiver:
            print_fail("存档系统未初始化")
            return
        
        prob_dir = os.path.join(self.archiver.solutions_dir, pid)
        if not os.path.isdir(prob_dir):
            print_fail(f"题目 {pid} 还没有存档")
            return
        
        print_header(f"题目 {pid} 存档内容")
        
        files = os.listdir(prob_dir)
        for f in sorted(files):
            fpath = os.path.join(prob_dir, f)
            size = os.path.getsize(fpath)
            print(f"  {Colors.BLUE}{f}{Colors.RESET}  ({size} 字节)")
        
        print()
        print_info("支持的命令:")
        print_dim("  open <文件名>   - 用默认程序打开文件")
        print_dim("  例: open README.md")
        print_dim("  例: open solution.cpp")

    def cmd_solutions(self, args):
        """solutions - 列出所有存档"""
        if not self.archiver:
            print_fail("存档系统未初始化")
            return
        
        sol_dir = self.archiver.solutions_dir
        if not os.path.exists(sol_dir):
            print_warn("还没有存档记录")
            return
        
        dirs = []
        for d in os.listdir(sol_dir):
            dpath = os.path.join(sol_dir, d)
            if os.path.isdir(dpath) and d.isdigit():
                # 检查是否有 README
                has_readme = os.path.exists(os.path.join(dpath, 'README.md'))
                has_code = os.path.exists(os.path.join(dpath, 'solution.cpp'))
                dirs.append((int(d), d, has_readme, has_code))
        
        if not dirs:
            print_warn("还没有存档记录")
            return
        
        dirs.sort(key=lambda x: x[0])
        
        print_header(f"本地存档 ({len(dirs)} 道题)")
        print(f"  {Colors.DIM}{'题号':<8} {'笔记':<6} {'代码':<6}{Colors.RESET}")
        print(f"  {'-' * 24}")
        for _, d, has_rm, has_cpp in dirs:
            rm_mark = f"{Colors.GREEN}✓{Colors.RESET}" if has_rm else f"{Colors.DIM}-{Colors.RESET}"
            cpp_mark = f"{Colors.GREEN}✓{Colors.RESET}" if has_cpp else f"{Colors.DIM}-{Colors.RESET}"
            print(f"  {Colors.BOLD}{d:<8}{Colors.RESET} {rm_mark:<6} {cpp_mark:<6}")
        
        print()
        print_dim(f"  路径: {sol_dir}")
        print_dim(f"  使用 view <题号> 查看详情")

    def cmd_stats(self, args):
        """stats - 显示刷题统计"""
        print_header("刷题统计")
        
        # EOJ 上的题
        eoj_dir = os.path.join(BASE_DIR, 'eoj')
        eoj_count = 0
        if os.path.isdir(eoj_dir):
            problems = self.engine.list_existing_cpp_problems(eoj_dir)
            eoj_count = len(problems)
        
        # 存档中的题
        archived_count = 0
        if self.archiver and os.path.exists(self.archiver.solutions_dir):
            archived_count = len([d for d in os.listdir(self.archiver.solutions_dir)
                                if os.path.isdir(os.path.join(self.archiver.solutions_dir, d))
                                and d.isdigit()])
        
        print(f"  {Colors.BOLD}已做题目:{Colors.RESET} {eoj_count}")
        print(f"  {Colors.BOLD}已存档题目:{Colors.RESET} {archived_count}")
        if eoj_count > 0:
            print(f"  {Colors.BOLD}归档率:{Colors.RESET} {archived_count/eoj_count*100:.1f}%")
        
        # 如果有 index.md，显示 AC 情况
        if self.archiver:
            index_path = os.path.join(self.archiver.solutions_dir, 'index.md')
            if os.path.exists(index_path):
                ac_count = 0
                with open(index_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        if '✅' in line:
                            ac_count += 1
                if ac_count > 0:
                    print(f"  {Colors.BOLD}已通过 (AC):{Colors.RESET} {ac_count}")

    def cmd_clear(self, args):
        """clear - 清屏"""
        os.system('cls' if os.name == 'nt' else 'clear')
        print_banner()

    def cmd_help(self, args):
        """help - 显示帮助信息"""
        print_header("命令帮助")
        help_text = f"""
{Colors.BOLD}刷题相关:{Colors.RESET}
  {Colors.GREEN}solve <题号>{Colors.RESET}        刷单道题，自动生成代码、测试、提交、归档
        例: {Colors.DIM}solve 1001{Colors.RESET}
  {Colors.GREEN}batch <范围>{Colors.RESET}        批量刷题，自动处理多道题
        例: {Colors.DIM}batch 1001-1020{Colors.RESET}

{Colors.BOLD}归档相关:{Colors.RESET}
  {Colors.GREEN}archive <题号>{Colors.RESET}      对已有代码生成中文刷题笔记（不用重新刷）
        例: {Colors.DIM}archive 1001{Colors.RESET}
  {Colors.GREEN}archive <范围>{Colors.RESET}      批量归档
        例: {Colors.DIM}archive 1001-1020{Colors.RESET}
  {Colors.GREEN}archive all{Colors.RESET}         归档 eoj/ 目录中全部已有题目

{Colors.BOLD}查看相关:{Colors.RESET}
  {Colors.GREEN}solutions{Colors.RESET}           列出所有本地存档
  {Colors.GREEN}view <题号>{Colors.RESET}         查看某道题的存档文件
  {Colors.GREEN}stats{Colors.RESET}               显示刷题统计

{Colors.BOLD}模型 / 接口:{Colors.RESET}
  {Colors.GREEN}models{Colors.RESET}              探测接入点支持的模型
  {Colors.GREEN}models <名称>{Colors.RESET}       切换当前使用的模型
  {Colors.GREEN}doctor{Colors.RESET}              环境自检（依赖 / 编译器 / 模型接口）

{Colors.BOLD}系统相关:{Colors.RESET}
  {Colors.GREEN}login{Colors.RESET}               登录 EOJ
  {Colors.GREEN}status{Colors.RESET}              查看系统状态（登录/模型/g++/存档）
  {Colors.GREEN}clear{Colors.RESET}               清屏
  {Colors.GREEN}help{Colors.RESET}                显示此帮助
  {Colors.GREEN}exit{Colors.RESET}                退出程序
  {Colors.GREEN}quit{Colors.RESET}                退出程序

{Colors.DIM}提示: 按 Ctrl+C 可中断正在执行的任务{Colors.RESET}
"""
        print(help_text)

    def cmd_exit(self, args):
        """exit/quit - 退出程序"""
        print()
        print_ok("再见！")
        self.running = False

    def cmd_empty(self, args):
        """空命令"""
        pass

    def cmd_open(self, args):
        """open <文件> - 用默认程序打开存档中的文件（只能在 view 上下文使用）"""
        # 这里实现为快捷文件打开
        if not args:
            print_warn("用法: open <文件路径>")
            return
        fpath = args[0]
        full_path = os.path.join(BASE_DIR, fpath)
        if not os.path.exists(full_path):
            # 尝试在 eoj_solutions 中查找
            full_path = os.path.join(self.archiver.solutions_dir, fpath) if self.archiver else None
            if not full_path or not os.path.exists(full_path):
                print_fail(f"文件不存在: {fpath}")
                return
        try:
            os.startfile(full_path)
            print_ok(f"已打开: {full_path}")
        except Exception as e:
            print_fail(f"无法打开: {e}")

    # ============================================================
    # 命令解析与执行
    # ============================================================

    def parse_and_execute(self, line):
        """解析并执行命令"""
        line = line.strip()
        if not line:
            return
        
        # 分割命令和参数
        parts = line.split()
        cmd_name = parts[0].lower()
        cmd_args = parts[1:] if len(parts) > 1 else []
        
        # 处理别名
        if cmd_name in self.command_aliases:
            cmd_name = self.command_aliases[cmd_name]
        
        # 处理特殊命令 open (可直接执行)
        if cmd_name == 'open':
            self.cmd_open(cmd_args)
            return
        
        # 查找命令处理器
        handler = self.commands.get(cmd_name)
        if handler:
            try:
                handler(cmd_args)
            except KeyboardInterrupt:
                print_warn("\n操作已中断")
        else:
            print_fail(f"未知命令: {cmd_name}")
            print_dim("输入 help 查看可用命令")

    def input_with_history(self, prompt):
        """带历史记录的命令行输入（仅限交互式控制台，不适用于管道）"""
        import msvcrt
        chars = []
        history = self.history
        current_line = ''

        sys.stdout.write(prompt)
        sys.stdout.flush()

        while True:
            try:
                ch = msvcrt.getwche()
            except:
                print()
                return input()  # fallback

            if ch == '\r':
                print()
                break
            elif ch == '\b' or ord(ch) == 127:
                if chars:
                    chars.pop()
                    sys.stdout.write(' \b')
                    sys.stdout.flush()
                    current_line = ''.join(chars)
                continue
            elif ch == '\xe0':
                try:
                    ch2 = msvcrt.getwche()
                    if ch2 == 'H':
                        prev = history.get_prev()
                        if prev is not None:
                            back = len(current_line)
                            sys.stdout.write('\b' * back + ' ' * back + '\b' * back)
                            sys.stdout.write(prev)
                            sys.stdout.flush()
                            chars = list(prev)
                            current_line = prev
                    elif ch2 == 'P':
                        nxt = history.get_next()
                        if nxt is not None:
                            back = len(current_line)
                            sys.stdout.write('\b' * back + ' ' * back + '\b' * back)
                            sys.stdout.write(nxt)
                            sys.stdout.flush()
                            chars = list(nxt)
                            current_line = nxt
                except:
                    pass
                continue
            elif ch == '\x03':
                print('^C')
                return ''
            elif ch == '\x1a':
                print()
                return ''
            else:
                # 普通字符：存到 chars 中（getwche 已自动回显）
                chars.append(ch)
            current_line = ''.join(chars)
        return current_line

    def is_piped_input(self):
        """检测是否来自管道/重定向输入"""
        try:
            return not os.isatty(sys.stdin.fileno())
        except:
            return False

    #: UTF-8 BOM（EF BB BF）被按 GBK 解错后留下的残渣。
    #: 具体字样取决于解码器的错误处理（可能是「锘縟」+ 替换字符），
    #: 因此只匹配 U+9518 后面跟一个 CJK 区字符这种可识别的形态。
    _MANGLED_BOM_RE = re.compile(r'^\u9518[\ufffd]?[\u4e00-\u9fff]')

    @classmethod
    def _normalize_line(cls, line):
        """清洗管道输入的一行。

        Windows 上把命令用管道喂进来时，首行常常带 UTF-8 BOM。除了在文件顶部
        把 stdin 重配成 ``utf-8-sig``，这里再做一层兜底：万一 BOM 已经被按 GBK
        解成「锘縟」之类的乱码，也剥掉，避免第一条命令变成「未知命令」。
        """
        if line is None:
            return ''
        text = line.replace('\x00', '')          # PowerShell 5.1 管道可能掺入 NUL
        text = text.lstrip('\ufeff')             # 正常解出的 BOM
        text = cls._MANGLED_BOM_RE.sub('', text)  # 被 GBK 解错的 BOM
        return text.strip()

    def run(self):
        """运行控制台主循环"""
        if not self.initialize():
            print_fail("初始化失败，请检查配置")
            return

        is_piped = self.is_piped_input()
        if is_piped:
            # 管道输入模式 - 使用普通 input
            print_header("管道输入模式")
            print_info("从管道读取命令...")
            print()
            for raw in sys.stdin:
                line = self._normalize_line(raw)
                if not line:
                    continue
                print(f"{self.PROMPT}{line}")
                self.history.add(line)
                self.parse_and_execute(line)
                if not self.running:
                    break
            return

        print_header("准备就绪")
        print_info("输入 help 查看命令列表")
        print()

        while self.running:
            try:
                # 交互式模式 - 使用自定义历史输入
                try:
                    import msvcrt
                    line = self.input_with_history(self.PROMPT)
                except ImportError:
                    line = input(self.PROMPT)

                self.history.add(line)
                self.parse_and_execute(line)

            except KeyboardInterrupt:
                print(f"\n{Colors.YELLOW}[!] 按 Ctrl+C 退出程序? (y/n): {Colors.RESET}", end='')
                try:
                    if input().strip().lower() == 'y':
                        self.running = False
                        print_ok("再见！")
                except KeyboardInterrupt:
                    self.running = False
                    print_ok("再见！")
            except EOFError:
                print()
                self.running = False
                print_ok("再见！")
            except Exception as e:
                print_fail(f"错误: {e}")
                import traceback
                traceback.print_exc()


# ============================================================
# 快速命令模式（直接从命令行参数执行单条命令）
# ============================================================

def quick_command():
    """命令行模式：直接执行传入的命令"""
    if len(sys.argv) < 2:
        return False
    
    cmd = ' '.join(sys.argv[1:])
    print(f"快速命令: {cmd}\n")
    
    console = EOJConsole()
    if not console.initialize():
        return True
    
    console.parse_and_execute(cmd)
    return True


# ============================================================
# 入口
# ============================================================

def main():
    if len(sys.argv) > 1:
        # 命令行模式：python eoj_cli.py solve 1001
        sys.exit(0 if quick_command() else 1)
    else:
        # 交互模式
        console = EOJConsole()
        console.run()


if __name__ == '__main__':
    main()
