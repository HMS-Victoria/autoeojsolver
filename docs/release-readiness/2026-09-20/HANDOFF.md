# 任务 06 交接记录（2026-09-20）

负责人：Codex 任务 01a0beb8-2cd0-7293-b6c4-983a135de11f；只修改 autoeojsolver。任务单为 release-audit-2026-09-20/tasks/06_autoeojsolver.md，同级 eoj_auto_solver_project 及其他任务单未修改。

源码基线：698a65025cb561823adea662d4194e0cde4c3e4c，开工工作区干净。版本 4.0.1，未创建新 Git 提交；当前源码见 release/EOJSolver-4.0.1-source.zip，运行时代码 SHA256 见 release/SOURCE_MANIFEST.json；source.patch 仅记录跟踪文件差异，新增文件在源码 ZIP。开工远端 Release 查询为 []，见 remote-releases.json；未进行推送或发布。

## 当前实现

- 保留原 Tkinter 界面，新增首次设置说明、自检按钮与便携入口。
- 完整私有 MSYS2 UCRT GCC 16.2.0-3 / MinGW-w64 14，17 个依赖包、完整头文件和库。必须保留 toolchain/ucrt64 的官方目录名，不能改为 mingw64；保留了旧 mingw64 查找兼容。优先包内编译器，仅子进程增加 bin 到 PATH。
- 缺编译器、跳过测试、无样例、零次尝试或中途失效均为 UNVERIFIED 并阻断提交；非零退出即使输出匹配也不得通过。
- GUI 和 CLI 默认不提交；CLI 的 --submit 为明确选择。冻结程序配置和题解保存于 %LOCALAPPDATA%/EOJSolver，EOJ_DATA_DIR 可指定隔离目录。没有打包作者数据或凭据。
- 15 份完整工具链源码包包含原始源码/固定 Git 提交、补丁、PKGBUILD 与 .SRCINFO。74 项源码核验通过，59 份补充许可及原始 notices 保留。与 GUI ZIP 一起发布源码配套 ZIP；不声称已做逐字节重建。

## 交付目录

release/ 集中 GUI ZIP、应用源码 ZIP、工具链源码 ZIP、说明和 SHA256SUMS。最新 GUI 精确大小、文件数及哈希见本目录 package-audit.json；配套源码见 toolchain-source-asset.json。所有最终文件哈希以 release/SHA256SUMS 为准，避免把本交接文件的历史数字误当最终摘要。

build/、dist/、.venv/ 为隔离构建/下载/验证目录。旧 WinLibs 候选、源码追溯材料和旧验证摘要保存在 build/retired-winlibs-review；早期 WinLibs 日志仍在本目录，仅作历史记录。当前候选完全采用 MSYS2，无两种工具链混用。

## 验证与边界

215 项测试通过（43.76 秒），见 pytest-msys2-final.txt / .xml。冻结程序在系统 PATH、独立用户数据与 TEMP 下实际 C++17 编译及两组样例通过，离线站点/模型成功和失败路径、OCR 模型初始化、隐藏窗口构造及默认不提交均通过。最终 ZIP 重新解压到带空格英文路径再运行，证据见 package-audit.json、relocated-selftest.json。具体限制见 VERIFICATION.md。

中文程序与中文 TEMP 组合仍会导致汇编临时文件创建失败，程序提示并阻断提交。程序和临时目录要求纯英文。隐藏窗口检查不代表可见界面、输入法、缩放或多屏验收。

用户明确回复：“没有现成环境，保留该验收待办”。因此本地交付收尾后，干净 Windows 10/11 x64（无 Python/g++）验收作为经用户接受的后续待办。没有把本机进程隔离当干净机器。真实模型连接、站点登录/验证码和人工界面另行验收；本轮没有真实提交。

## 复现与下一步

按 requirements-build.lock 在项目 .venv 安装构建依赖。脚本入口依次为：

1. scripts/prepare_toolchain.py：按固定官方 URL/哈希下载并解压 17 个二进制包及 15 个完整源码包，不执行上游构建配方。
2. scripts/build_portable.py --toolchain build/msys2-toolchain/ucrt64：生成 dist/EOJSolver；完整许可文本随应用源码快照提供。
3. scripts/verify_portable.py dist/EOJSolver docs/release-readiness/2026-09-20/portable-selftest.json：测试真实 EXE。
4. scripts/audit_toolchain_sources.py：核验源码并生成工具链源码 ZIP。
5. scripts/package_release.py：工具链文件集/逐文件哈希对照、生成 GUI ZIP、CRC、全新路径解压复测。若 build/msys2 relocated acceptance/EOJSolver 已存在，先保留旧验证副本并选择新目录，脚本拒绝混入旧文件。
6. scripts/archive_release.py：源码快照、文档、最终哈希；运行时代码必须与包内 SOURCE_MANIFEST 一致。

开发机构建时需能读取 Python 安装中的 Tcl/Tk；本机构建设置 TCL_LIBRARY 和 TK_LIBRARY 为 Python312/tcl/tcl8.6、tk8.6。此设置不传入最终自检进程；不要忽略 tkinter installation is broken 后仍称打包成功。

后续有干净机器时按 VERIFICATION.md 补验收；若用户授权发布，再上传 GUI、两个源码包、说明及 SHA256SUMS，并从公开链接回取核对。没有既有远端发布授权，不应自动推送。

## 2026-09-21 发布授权更新

用户已明确要求“发布吧”。上文未授权/未提交状态是 2026-09-20 构建阶段记录。当前按预发布上传，干净机器待办不变。发布过程和最终链接见 ../2026-09-21/HANDOFF.md。
