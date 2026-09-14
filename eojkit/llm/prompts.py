# -*- coding: utf-8 -*-
"""
eojkit.llm.prompts —— 解题 / 笔记 / 纠错提示词模板
===================================================

把原先散落在 ``DeepSeekSolver`` 三个方法里的 f-string 抽出来集中管理，
便于统一调优与复用。新增 ``PROMPT_VERSION`` 版本号，方便笔记回溯生成规则。

Designed by HMS_Victorious
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence

__all__ = [
    "PROMPT_VERSION",
    "SYSTEM_CODER",
    "SYSTEM_NOTE",
    "format_samples",
    "format_samples_markdown",
    "build_code_prompt",
    "build_fix_prompt",
    "build_note_prompt",
    "build_analysis_prompt",
]

PROMPT_VERSION = "4.0"

SYSTEM_CODER = (
    "You are a competitive programming expert. "
    "Write clean, efficient, self-contained C++ solutions. "
    "Never wrap the final code in explanations."
)

SYSTEM_NOTE = "你是一名算法竞赛刷题高手，擅长用中文写清晰易懂的刷题笔记。"


def format_samples(samples: Sequence[Dict[str, str]], markdown: bool = False) -> str:
    """把样例列表格式化成提示词片段。"""
    chunks: List[str] = []
    for index, sample in enumerate(samples or [], start=1):
        data_in = (sample or {}).get("input", "") or ""
        data_out = (sample or {}).get("output", "") or ""
        if markdown:
            chunks.append(
                f"**样例 {index} 输入:**\n```\n{data_in}\n```\n"
                f"**样例 {index} 输出:**\n```\n{data_out}\n```"
            )
        else:
            chunks.append(
                f"Sample Input {index}:\n{data_in}\n"
                f"Sample Output {index}:\n{data_out}"
            )
    return "\n".join(chunks)


def format_samples_markdown(samples: Sequence[Dict[str, str]]) -> str:
    return format_samples(samples, markdown=True)


def build_code_prompt(problem_info: Dict) -> str:
    """首次生成解题代码的提示词。"""
    description = problem_info.get("description", "")
    sample_text = format_samples(problem_info.get("samples") or [])
    return f"""You are a competitive programmer. Solve the following problem and write a C++ solution.

Problem Description:
{description}

{sample_text}

Requirements:
1. Write complete C++ code that reads from stdin and writes to stdout
2. Use `using namespace std;`
3. Only output the code, no explanations
4. The code must pass the sample tests
5. Handle multiple test cases if needed (read until EOF)
6. Use appropriate data types (long long, big integer, etc.)
7. Include required headers (<iostream>, <string>, <vector>, etc.)
8. Add Chinese comments to explain key parts of the code
9. The code MUST compile with g++ -std=c++17 without warnings when possible
10. Return the code inside a single ```cpp fenced block"""


def build_fix_prompt(problem_info: Dict, previous_code: str, error_info: str) -> str:
    """根据编译/测试错误让模型修代码的提示词。"""
    description = problem_info.get("description", "")
    sample_text = format_samples(problem_info.get("samples") or [])
    return f"""You are a competitive programmer. The previous C++ solution for the following problem FAILED.

## Problem Description:
{description}

{sample_text}

## Previous Code (FAILED):
```cpp
{previous_code}
```

## Error Message:
{error_info}

Please fix the code. Analyze the error carefully and provide a corrected C++ solution.
Requirements:
1. Write complete C++ code that reads from stdin and writes to stdout
2. Use `using namespace std;`
3. Only output the code, no explanations
4. The code must pass the sample tests
5. Handle multiple test cases if needed (read until EOF)
6. Use appropriate data types (long long for large numbers, etc.)
7. Fix ALL issues mentioned in the error message above
8. Add Chinese comments to explain key parts
9. Return the code inside a single ```cpp fenced block"""


def build_note_prompt(problem_info: Dict, code: Optional[str] = None) -> str:
    """生成中文刷题笔记的提示词。"""
    description = problem_info.get("description", "")
    sample_text = format_samples_markdown(problem_info.get("samples") or [])
    problem_id = problem_info.get("id", "")
    title = problem_info.get("title", "")

    include_code = bool(code)
    code_instruction = (
        "5. 笔记正文不要重复粘贴完整代码（代码已单独保存为 solution.cpp）"
        if include_code
        else "5. 若题目需要关键代码片段，最多给出 5 行以内的核心片段"
    )

    return f"""你是一名算法竞赛选手，请为以下题目写一份**中文刷题笔记**（风格类似个人错题本/复习笔记）。

## 题目描述
{description}

{sample_text}

请按以下格式输出（使用 Markdown）：

# 题目 {problem_id} - {title}

## 题目大意
[用一两句话概括题目]

## 解题思路
[分步骤说明解题思路，包括如何推导、为什么这么想]

## 算法分析
- **算法/数据结构**: [如 贪心、DP、BFS、并查集 等]
- **时间复杂度**: O(?)
- **空间复杂度**: O(?)

## 关键点
- [列出实现时需要注意的关键点]
- [容易踩坑的地方]

## 代码解析
[逐段解释核心代码逻辑]

注意：
1. 全程使用中文撰写
2. 语言简洁清晰，就像给自己看的笔记
3. 重点放在"为什么这么解"而不是"怎么解"
4. 直接输出 Markdown 正文，不要用 ```markdown 围栏包裹，不要输出多余寒暄
{code_instruction}"""


def build_analysis_prompt(problem_info: Dict, code: Optional[str] = None) -> str:
    """向后兼容别名。"""
    return build_note_prompt(problem_info, code)
