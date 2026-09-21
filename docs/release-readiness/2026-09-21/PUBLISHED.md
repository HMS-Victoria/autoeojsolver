# 发布完成记录（2026-09-21）

Release：https://github.com/HMS-Victoria/autoeojsolver/releases/tag/v4.0.1

标签 v4.0.1，预发布；应用源码提交 `0103ba2cba6e269528093aa4225901690b010944`。9 个附件已公开，包括 GUI ZIP、应用源码、完整工具链源码、使用说明、第三方材料、验证说明及哈希。GitHub 端摘要与本地一致，匿名公开下载回取 9 项 SHA256 全部通过；回取 GUI ZIP 的 CRC、完整解压后实际 EXE 编译/离线流程/OCR/隐藏 GUI 检查通过。

证据：publication-state.json、public-download-verification.json、public-package-selftest.json、source-commit.json、remote-tag.txt、PUBLISHED.json。回取文件保存在 build/public-download-2026-09-21，独立解压目录为 build/public package acceptance 2026-09-21。任务辅助脚本为 build/publish_release.py 与 build/check_public_package.py；凭据仅通过已有 GCM 在进程内使用，没有输出或保存。

运行时代码未变；215 项测试沿用上一日结果。本次仅同步发布文档和打包辅助入口。首次回取在工具链源码文件末段中断，重试后全部通过；没有覆盖已发布附件。主分支后续文档提交只补充本发布结果，v4.0.1 标签仍固定在应用源码提交。

干净 Windows 无 Python/g++ 验收按用户要求继续保留待办；可见 GUI、缩放、输入法、真实服务仍待人工验收。程序和临时目录须纯英文。本轮没有真实题解提交。发布为预发布，不宣称完成真实新电脑验收。
