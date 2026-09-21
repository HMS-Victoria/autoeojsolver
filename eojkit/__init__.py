# -*- coding: utf-8 -*-
"""EOJ 自动刷题系统核心库。

模块划分::

    eojkit
    ├── config.py          配置中心（环境变量 / .env / JSON 分层）
    ├── llm/               大模型接入层（本次重构重点）
    │   ├── client.py      OpenAI 兼容客户端：重试 / 降级 / 推理模型支持
    │   ├── prompts.py     提示词模板
    │   └── solver.py      AI 解题与笔记生成
    ├── judge/             EOJ 站点交互（登录 / 抓题 / 提交 / 判题）
    ├── asm.py             本地编译测试
    ├── archive.py         笔记归档
    └── tools.py           通用工具与日志

Designed by HMS_Victorious
"""

__version__ = "4.0.1"
__all__ = ["__version__"]
