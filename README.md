> **2026-09-20 / 4.0.1 portable candidate:** Windows GUI packaging and safety fixes are recorded in [release readiness](docs/release-readiness/2026-09-20/HANDOFF.md). GUI and CLI now default to no submission; use `--submit` explicitly for CLI submission. Unverified code is blocked. The package includes private MSYS2 GCC and its matching source companion. Clean-machine and visible GUI acceptance remain pending; the user approved deferring clean-machine acceptance. The Windows build is distributed as a prerelease with these acceptance limitations.

<div align="center">

# EOJ Auto Solver

**一个端到端自动做题系统：登录评测机 → 抓题 → 大模型生成 C++ → 本地编译测试 → 闭环重写 → 提交判题 → 归档中文题解**

[![Python](https://img.shields.io/badge/Python-3.8%2B-3776ab?logo=python&logoColor=white)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/tests-215%20passed-success)](tests/)
[![Offline](https://img.shields.io/badge/test%20suite-100%25%20offline-informational)](tests/)
[![Version](https://img.shields.io/badge/eojkit-v4.0.1-blue)](eojkit/__init__.py)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

[English](#english) · [中文](#中文) · [架构](#architecture--架构) · [快速开始](#quick-start--快速开始)

</div>

---

## English

### What this is

`eoj_auto_solver` drives the full **problem-solving loop against a live online judge** with no human in
the middle. Given a problem ID, it logs into the ECNU Online Judge (`acm.ecnu.edu.cn`), scrapes the
statement and *all* sample cases, asks an OpenAI-compatible LLM for a C++17 solution, compiles it with
`g++ -O2 -Wall`, runs it against every sample, feeds compilation/test failures back to the model for up
to 3 rewrite rounds, submits the result, polls for a verdict, and writes a structured Chinese
editorial (`README.md`) plus six archival files per problem.

The interesting engineering is not "call an LLM" — it is everything around it: an auth flow that is
hostile to automation, model APIs that silently return empty bodies, and the fact that a wrong
solution must be caught locally *before* it pollutes a real judge account.

### Verified results

| Metric | Value |
|---|---|
| Production Python | **~8,100 lines** across 10 modules |
| Test suite | **206 test cases, 206 passed**, fully offline (no network, no API key) |
| Real runs, **no human intervention** | **46 archived problems**: 39 generated `solution.cpp`, 27 generated Chinese editorials, 38 local compile+sample test reports |
| Algorithmic coverage | Dinic max-flow + binary search on answer (`1116`), Hungarian bipartite matching (`21`), bipartite 2-coloring (`12`), DP — LIS/LCS/interval (`7`, `14`, `19`, `1051`, `1172`, `1184`), big-integer arithmetic (`5`, `18`, `1001`, `1119`), stack-based expression parsing (`1003`), string hashing (`14`, `1119`), bitmask search (`20`), geometry (`21`, `1184`) |
| Front ends | CLI (24 flags), interactive console (16 commands), Tkinter GUI |

The archive is committed under [`solutions/`](solutions/index.md) with a generated index — it is real
output, not a mock-up.

### Three problems worth highlighting

**1. The judge's login is designed to stop scripts — solved without weakening it.**
The login form requires a CSRF token, a captcha, and the password **RSA-OAEP (SHA-256) encrypted
against an ephemeral public key embedded in the login page**. On top of that the captcha is an
*arithmetic word problem* rendered as an image (`3 times 7`). The system scrapes the public key,
re-wraps it as PEM, encrypts with `pycryptodome`, and solves the captcha with `ddddocr` plus a
recovery layer for OCR confusions (`times`→`*`, `T`→`7`, `s`→`5`, `O`→`0`, and "4time55"→`4×5`
de-duplication). Captcha failures retry with a fresh image rather than giving up.

**2. Reasoning-model APIs fail in a way that looks like success.**
`deepseek-v4-pro`-class models put the chain of thought in `reasoning_content`, so a response can come
back HTTP 200 with an **empty `content`** because the thinking budget consumed `max_tokens`. Naively
parsing that yields "AI returned nothing". The client detects the condition, doubles the token budget
(capped at 32,768, up to 4× the base) and retries; it also accepts a response truncated at
`finish_reason=length` when a brace/backtick-balance heuristic says the body is actually complete. On
top of that: 401/403 are never retried, 429 and 5xx use exponential backoff with jitter (2/4/8/16 s,
capped at 30 s), and a failure cascade degrades to `fallback_models`.

**3. A wrong answer must be caught before it reaches the judge.**
Compile and run every sample locally first, and on failure send the *actual* compiler error and the
first failing sample (expected vs. actual) back to the model for a rewrite — up to 3 rounds. Getting
this right exposed a class of bugs that a naive implementation ships: a shared `requests.Session`
across 4 worker threads, a sample-extraction bug that silently kept only the **first** `div.example`
so multi-sample problems were "tested" against one case, a `"Runtime Error"` verdict misclassified as
TLE because `"Time"` matched first, and a pipeline that **skipped testing and submitted anyway**
whenever the compiler lookup returned `None`.

### Architecture

```
Input: problem id / range / contest
  │
  ├─ EOJClient.login()          CSRF → RSA-OAEP(SHA-256) password → captcha OCR (auto-retry on new image)
  ├─ get_problem_info()         statement + ALL samples (find_all, with table fallback)
  ├─ DeepSeekSolver.generate_code()   LLM → fenced-code extraction → C++17
  │
  ├─ CodeTester.build()         g++ -std=c++17 -O2 -Wall   (30 s timeout)
  ├─ CodeTester.test_with_samples()   per-sample diff, whitespace/CRLF-normalized (5 s timeout)
  │     │
  │     └─ on failure ──► solver.regenerate_code(problem, code, error_report)   ×3 rounds
  │
  ├─ EOJClient.submit()         POST + verdict polling every 2 s
  └─ SolutionArchiver           statement.txt · samples.txt · solution.cpp ·
                                README.md (Chinese editorial) · test_result.txt · meta.json
                                + atomically rebuilt index.md
```

| Module | Lines | Responsibility |
|---|---|---|
| `eojkit/judge/client.py` | 947 | Login (CSRF + RSA-OAEP + captcha), scraping, multi-sample extraction, submission, verdict polling, contest mode |
| `eojstart.py` | 1,791 | Tkinter GUI: provider/model probing, live log sink, task control |
| `eoj_cli.py` | 997 | Interactive console with command history |
| `eojkit/llm/client.py` | 675 | OpenAI-compatible client: retries, backoff+jitter, model degradation, reasoning models, SSE streaming |
| `eojkit/tools.py` | 590 | Logging sinks, captcha OCR + arithmetic recovery, `g++` detection, temp-dir policy |
| `eojkit/config.py` | 553 | Layered config (CLI > env/.env > JSON > defaults), 7 provider presets, secret masking |
| `eojkit/archive.py` | 524 | Note archiving, atomic writes, idempotent metadata footer, index rebuild/repair |
| `eojkit/pipeline.py` | 477 | The solve loop, structured `SolveOutcome`, batch runner |
| `eojkit/asm.py` | 414 | Compile + sample testing, legacy-compatible result views |
| `eojkit/llm/solver.py` | 209 | Code generation, rewrite-on-error, editorial generation |
| `eojkit/llm/prompts.py` | 164 | Prompt templates (code / fix / editorial) |

### Testing: 206 cases, zero network

The suite spins up **local HTTP servers that impersonate both the OpenAI API and the EOJ site**, so
every branch is exercised without a network, an API key, or an account:

```
$ python -m pytest -q
206 passed in 36s
```

Covered: retry/degradation paths, empty-body reasoning responses, truncation-driven token escalation,
multi-sample extraction, verdict mapping, caption OCR arithmetic recovery, archival + index
round-trips, GUI construction/callback smoke test, console input normalization, and the
backward-compatibility layer. Tests needing `g++` skip automatically when no compiler is present.

### Quick start

```bash
git clone https://github.com/HMS-Victoria/autoeojsolver.git
cd autoeojsolver
pip install -r requirements.txt
```

Credentials come from the environment — **never from source**:

```bash
# Linux / macOS
export EOJ_USERNAME="your@stu.ecnu.edu.cn"
export EOJ_PASSWORD="..."
export LLM_API_KEY="sk-..."

# Windows PowerShell
$env:EOJ_USERNAME="your@stu.ecnu.edu.cn"
$env:EOJ_PASSWORD="..."
$env:LLM_API_KEY="sk-..."
```

Or copy `.env.example` to `.env`. Then:

```bash
python eoj_auto_solver.py --doctor              # self-check: deps, g++, model endpoint
python eoj_auto_solver.py --list-models         # query the endpoint for real model IDs
python eoj_auto_solver.py --problem 1001        # solve one problem end-to-end
python eoj_auto_solver.py --problem 1001 --no-submit   # generate + test locally, don't submit
python eoj_auto_solver.py --range 1001-1020     # batch
python eoj_auto_solver.py --contest 1021 --all  # whole contest
python eoj_auto_solver.py --rebuild-index       # rebuild solutions/index.md from meta.json
python eojstart.py                              # GUI
python eoj_cli.py                               # interactive console
```

**Any OpenAI-compatible endpoint works** — switching provider means changing `base_url` + `model`
(7 presets: DeepSeek, SiliconFlow, Moonshot, DashScope, OpenAI, Ollama, custom). Local `g++` (C++17)
is required for the local test stage; without it the tool warns loudly instead of pretending to test.

### Configuration precedence

```
CLI flags  >  env vars / .env  >  eoj_config.json  >  built-in defaults (contains no secrets)
```

Keys are masked in logs and in the UI, `eoj_config.json` and `.env` are git-ignored, and intermittent
artifacts (source copies, executables, debug HTML, captcha images) are written to `%TEMP%\eojkit\`
rather than the repository.

### Notes & limitations

- **This is a personal practice/automation tool, not an attempt to game a judge.** Submissions are
  rate-limited (1 s default between problems) and the local test gate is meant to keep junk
  submissions off the judge.
- Captcha OCR is the least reliable link. EOJ uses arithmetic *word* problems that `ddddocr` was not
  trained on; batch mode retries with new images, and interactively the tool falls back to asking you.
- This is an **independent personal project**, not affiliated with or endorsed by ECNU.

---

## 中文

### 这是什么

`eoj_auto_solver` 把「做题」这件事整条链路自动化了：给它一个题号，它会登录华东师范大学在线评测
系统（`acm.ecnu.edu.cn`）、抓取题面与**全部**样例、让大模型生成 C++17 解法、用 `g++ -O2 -Wall`
真实编译并逐个样例测试，失败就把**真实的编译报错 / 首个未过样例**回喂给模型重写（最多 3 轮），
然后提交、轮询判题结果，并为每道题归档一份中文题解和 6 个结构化文件。

真正的工作量不在「调用大模型」，而在它周围的一切：一个处处与自动化对抗的登录流程、会**静默返回
空正文**的推理模型接口，以及「错的代码必须在本地就被拦住，而不是拿去污染真实账号的提交记录」。

### 实测数据

| 指标 | 数值 |
|---|---|
| 生产代码 | **约 8,100 行**，10 个模块 |
| 测试 | **206 个用例全部通过**，纯离线（不需要网络 / API Key / 账号） |
| **无人干预的真实运行产出** | **46 道题**已归档：39 份生成代码、27 篇中文题解、38 份本地编译+样例测试报告 |
| 覆盖的算法 | 二分答案 + Dinic 最大流（`1116`）、匈牙利算法二分图匹配（`21`）、二分图 BFS 染色（`12`）、DP/LIS/LCS/区间（`7` `14` `19` `1051` `1172` `1184`）、大数运算（`5` `18` `1001` `1119`）、栈式表达式解析（`1003`）、字符串哈希（`14` `1119`）、位运算搜索（`20`）、几何（`21` `1184`） |
| 三种入口 | 命令行（24 个参数）、交互式控制台（16 条命令）、Tkinter 图形界面 |

全部产出已提交在 [`solutions/`](solutions/index.md) 并附带自动生成的索引 —— 是真实运行结果，不是样例截图。

### 三个值得一提的技术问题

**1. 评测机的登录流程就是用来拦脚本的 —— 在没有削弱它的前提下解决。**
登录表单要求 CSRF token、验证码，以及**用登录页内嵌的一次性公钥做 RSA-OAEP(SHA-256) 加密的密码**；
验证码还不是普通字符，而是渲染成图片的**算术文字题**（如 `3 times 7`）。系统会抓取公钥并重新包装
成 PEM、用 `pycryptodome` 加密，再用 `ddddocr` 识别并叠加一层纠错：`times`→`*`、`T`→`7`、`s`→`5`、
`O`→`0`，以及把 OCR 重复字符还原（`4time55` 实为 `4×5`）。验证码错了会自动换一张新图重试，而不是直接放弃。

**2. 推理模型接口的失败方式，看起来像成功。**
`deepseek-v4-pro` 一类模型把思维链放在 `reasoning_content`，当思考过程吃掉 `max_tokens` 后，接口会
返回 HTTP 200 但 **`content` 为空**。朴素解析只会得到「AI 没返回内容」。客户端会识别这种情况，把
token 预算翻倍（上限 32,768，最多到基准的 4 倍）后重试；并用「花括号/反引号是否配对」判断正文其实
已完整，从而接受 `finish_reason=length` 的截断响应。此外：401/403 绝不重试，429 与 5xx 走指数退避 +
抖动（2/4/8/16 秒，封顶 30 秒），主模型连续失败自动降级到 `fallback_models`。

**3. 错的答案必须在上交之前被拦住。**
先在本地编译、逐个样例测试，失败时把**真实的编译错误**和**第一个未通过样例的期望值/实际值**回喂给
模型重写，最多 3 轮。把这件事做对，会暴露一批「朴素实现会直接上线」的缺陷：4 个工作线程共用一个
`requests.Session`；样例提取只取**第一个** `div.example`，导致多样例题其实只测了一个样例；判词
`"Runtime Error"` 被 `"Time"` 抢先匹配成 TLE；以及在编译器探测返回 `None` 时**跳过测试却照样提交**。

### 项目结构

```
autoeojsolver/
├── eojkit/                       核心库
│   ├── config.py                 分层配置 + 7 套供应商预设 + 密钥打码
│   ├── tools.py                  日志 sink、验证码识别与算术纠错、g++ 探测、临时目录策略
│   ├── asm.py                    本地编译与样例比对
│   ├── archive.py                题解归档、原子写入、索引重建/修复
│   ├── pipeline.py               解题主循环 + 批量调度
│   ├── llm/                      client.py（重试/降级/推理模型/流式）· solver.py · prompts.py
│   └── judge/client.py           登录/抓题/提交/判题（CSRF + RSA-OAEP + 验证码）
├── eoj_auto_solver.py            命令行入口 + 向后兼容层
├── eojstart.py                   Tkinter 图形界面
├── eoj_cli.py                    交互式控制台
├── tests/                        206 个离线用例
├── solutions/                    46 道题的归档产出 + index.md
└── research/                     早期页面探索脚本与竞赛页面快照（存档参考）
```

### 快速开始

```bash
git clone https://github.com/HMS-Victoria/autoeojsolver.git
cd autoeojsolver
pip install -r requirements.txt

# 凭据只从环境变量读取，源码中不存在任何硬编码密钥
$env:EOJ_USERNAME="your@stu.ecnu.edu.cn"     # Windows PowerShell
$env:EOJ_PASSWORD="..."
$env:LLM_API_KEY="sk-..."

python eoj_auto_solver.py --doctor            # 环境自检：依赖 / g++ / 模型接口
python eoj_auto_solver.py --problem 1001      # 完整跑一题
python eoj_auto_solver.py --problem 1001 --no-submit   # 只生成+本地测试，不提交
python eoj_auto_solver.py --range 1001-1020   # 批量
python eojstart.py                            # 图形界面
python eoj_cli.py                             # 交互式控制台
```

配置优先级：`命令行参数 > 环境变量 / .env > eoj_config.json > 内置默认值（不含任何密钥）`。
`.env` 与 `eoj_config.json` 已在 `.gitignore` 中；编译中间产物、调试 HTML、验证码图片统一落在
`%TEMP%\eojkit\`，不污染仓库。

### 测试

```bash
python -m pytest -q      # 206 passed
```

测试用**本地 HTTP 服务模拟 OpenAI 接口与 EOJ 站点**，因此不需要联网、不需要 API Key：
覆盖重试与降级、推理模型空正文、截断抬预算、多样例提取、判词映射、验证码算术纠错、归档与索引
往返、GUI 构建与回调冒烟、控制台输入清洗、兼容层行为等分支。需要 `g++` 的用例在缺少编译器时自动跳过。

### 说明与局限

- **这是一个个人练习/自动化工具，不是用来刷评测机排名的外挂。** 批量提交默认间隔 1 秒，本地测试
  这道闸门的目的正是尽量不把错误代码送去评测机。
- 验证码识别是最脆弱的一环：EOJ 用的是 `ddddocr` 未针对训练过的**算术文字题**；批量模式会自动
  换图重试，交互式则回退为人工输入。
- 本项目为**个人独立项目**，与华东师范大学官方无关。

---

<div align="center">

**Designed by [HMS_Victorious](https://github.com/HMS-Victoria)** · MIT License

</div>
