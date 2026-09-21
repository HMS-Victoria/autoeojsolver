EOJ 解题助手 4.0.1 Windows x64 预发布

普通用户下载 **EOJSolver-4.0.1-windows-x64-candidate.zip**，完整解压到纯英文目录（可含空格），双击 **EOJSolver.exe**。内含 Python/Tk、程序依赖和完整私有 MSYS2 UCRT GCC 16.2.0 / MinGW-w64 14，无需另外安装 Python 或 g++，不修改系统 PATH。

首次设置提供账号、模型服务、Key 配置提示和离线编译自检。GUI 与 CLI 默认不提交；缺少编译器、跳过测试、无样例或程序异常退出时均不得当作验证成功。需要真实服务时请自备 EOJ 账号和模型凭据；模型服务可能计费。

验证：215 项自动测试通过。真实便携程序在仅含 Windows 系统路径、独立数据和临时目录下完成 C++17 编译及样例测试；离线模拟流程、OCR 初始化、隐藏窗口构造及解压后运行通过。

**限制与待验收**：本版为预发布，尚未在无 Python/g++ 的干净 Windows 10/11 x64 机器验收；人工界面、缩放、输入法与真实登录/验证码/模型服务仍待验收。本轮没有真实题解提交。程序与临时目录必须使用纯英文路径；仅 x64、未签名。生成的代码以当前用户权限运行。

附带文件：
- EOJSolver-4.0.1-source.zip：与本版运行时代码对应的应用源码、构建脚本和测试。
- EOJSolver-4.0.1-toolchain-sources.zip：17 个工具链包所对应的 15 份完整源码包、补丁、构建配方和许可资料。请与 GUI 包一同保留。
- USER_GUIDE.md、VERIFICATION.md、THIRD_PARTY.md：使用方法、实际验证与第三方说明。
- SOURCE_MANIFEST.json：应用运行时代码哈希；SHA256SUMS：全部发布附件校验值。

GitHub 自动生成的 Source code 压缩包不是普通用户程序，请下载上方命名的 GUI ZIP。
