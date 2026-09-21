# 验证记录（2026-09-20）

## 当前候选的实际验证

平台：Windows 11 x64 10.0.26200；构建 Python 3.12.13、PyInstaller 6.22.3。当前工具链为 MSYS2 UCRT GCC 16.2.0-3 / MinGW-w64 14。未改变系统 PATH；构建依赖仅位于项目 .venv。

- 源码回归：215 passed，0 skipped，43.76 秒，见 pytest-msys2-final.txt / .xml。新增保护覆盖未验证不得提交、异常退出不得误判、两种包内目录优先级和默认不提交。旧 WinLibs 的 214 项记录仅为历史证据。
- 官方工具链：17 个完整包，binary SHA256 与官方下载页面一致；依赖闭包包括 gcc-libs 提供的 cc-libs 虚拟依赖。完整版本与哈希见 MSYS2_TOOLCHAIN_MANIFEST.json。
- 对应源码：15 个完整源码包；74 项原始源码、补丁或 Git 固定提交检查通过，见 MSYS2_SOURCE_VERIFICATION.json。原始源码、补丁、PKGBUILD、.SRCINFO 均在配套 ZIP 中。上游 SKIP 的签名文件只验证存在；未验证 PGP 签名，也未声称工具链可逐字节重建。59 份补充许可文本加原包 notices 已保留。
- 真实冻结 EXE：portable-selftest.json 中 frozen=true、ok=true、退出码 0。PATH 仅 Windows/System32 与 Windows，清除开发环境和模型/账号变量；数据与 TEMP 独立。实际编译包内 C++17 std::optional 样例，19+23=42、-3+8=5 通过。
- 离线流程：本地运行、模拟提交、跳过测试阻断、缺编译器阻断、模型失败、抓题失败通过。提交均为内存模拟或本地 HTTP 测试，未向真实站点提交。
- OCR 的 ONNX 模型实际初始化；Tk 窗口实际构造后隐藏，默认提交=false。隐藏窗口检查不等于人工交互验收。
- 最终 ZIP 的 CRC、工具链文件集合与逐文件 SHA256、用户数据排除和重新解压运行记录见 package-audit.json / toolchain-integrity.json / relocated-selftest.json。精确产物大小与哈希以 package-audit.json 和 release/SHA256SUMS 为准。

## 本轮发现与处理

- WinLibs 原方案缺少部分辅助工具的精确对应源码和构建环境版本，现已替换为附有完整对应源码包的 MSYS2 原生 Windows 工具链；旧候选与记录保存在 build/retired-winlibs-review，不再用于最终候选。
- 将 MSYS2 ucrt64 改名为 mingw64 导致 wchar.h 无法找到。保留官方目录名后修复；失败记录 msys2-renamed-prefix-failure.json。定位与打包脚本已同步修正。
- 早期普通隔离账号无法初始化开发机 Tcl，改用可读取 Tcl/Tk 的构建进程；最终冻结程序成功构造 Tk。普通隔离账号后续出现登录锁定错误，相关本仓库构建命令经权限审查后执行，未修改全局依赖。
- WinLibs 曾有中文路径 crt2.o 链接失败，unicode-path-failure.json 为历史记录；当前 MSYS2 在中文程序目录和中文 TEMP 组合下也未通过，汇编器无法创建临时目标文件，见 msys2-中文路径-selftest.json。保留纯英文程序及临时目录要求；失败被明确提示并阻止提交。
- PyInstaller 的 ddddocr 可选 FastAPI 服务端、ONNX 量化等开发组件警告不影响本包 OCR 推理；实际初始化检查通过。

## 明确保留的待办

用户回复“没有现成环境，保留该验收待办”：无 Python/g++ 的干净 Windows 10/11 x64 机器验收未执行。本机 Get-VM 返回 0，WindowsSandbox.exe 不存在。当前进程环境隔离不能替代干净机器。

可见窗口操作、缩放、多屏、中文输入、真实登录/验证码和真实模型账号需后续人工验收。本轮不进行真实题解提交。2026-09-21 用户已授权发布；公开上传与回取结果另存于 ../2026-09-21/，不改变以上环境验收结论。

## 干净机器步骤（后续）

1. 确认没有 Python/g++ 开发环境，记录系统版本，核对 SHA256SUMS。
2. 完整解压 GUI ZIP，双击 EOJSolver.exe，确认首次设置提示与默认不提交；点击离线自检。
3. 运行 EOJSolver.exe --self-test C:\eoj-acceptance\result.json --gui-smoke，检查 frozen=true、ok=true、compiler 路径位于包内。
4. 在测试副本中临时移开 toolchain，确认没有其他编译器时自检失败；恢复后重试。
5. 记录可见操作、显示缩放和中文输入。真实服务按用户授权另行验收，不擅自提交。保留原始结果到本目录。
