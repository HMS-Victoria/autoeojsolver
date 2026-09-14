# -*- coding: utf-8 -*-
# ============================================================================
# ⚠️ 历史存档脚本（v4.0 移入 legacy/，仅作参考，不参与主流程）
#
# 这些是最早期用于「摸清 EOJ 页面结构 / 验证 DeepSeek 接口」的一次性探索脚本。
# 对应的功能现在都由 eojkit 正规实现：
#     页面结构探索 → eojkit/judge/client.py
#     模型接口调用 → eojkit/llm/client.py
#
# 原本硬编码在文件里的账号 / 密码 / API Key 已在 v4.0 移除，
# 这里改为从环境变量读取（缺失时脚本会明确报错而不是静默使用空值）。
# ============================================================================

import os


def _require_env(*names):
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    raise SystemExit(
        "缺少环境变量 " + " / ".join(names) + "；请先设置后再运行该历史脚本。"
    )


EOJ_USERNAME = _require_env("EOJ_USERNAME")
EOJ_PASSWORD = _require_env("EOJ_PASSWORD")
DEEPSEEK_API_KEY = _require_env("DEEPSEEK_API_KEY", "LLM_API_KEY")

"""Research EOJ structure - comprehensive"""
import requests
import re
from bs4 import BeautifulSoup

# ====== 1. Problem page structure ======
print("=" * 60)
print("PROBLEM PAGE STRUCTURE")
print("=" * 60)

r = requests.get('https://acm.ecnu.edu.cn/problem/1001/', timeout=10)
soup = BeautifulSoup(r.text, 'html.parser')

# Title
title_el = soup.find('div', class_='title')
if title_el:
    print(f"Title: {title_el.text.strip()}")

# Problem body
problem_body = soup.find('div', class_='problem-body')
if problem_body:
    print(f"Problem body found! Length: {len(str(problem_body))}")
    
    # Description
    desc = problem_body.find('div', class_='description')
    if desc:
        print(f"Description: {desc.text.strip()[:200]}...")
    
    # Input/Output format
    for cls in ['input', 'output', 'input-specification', 'output-specification']:
        el = problem_body.find('div', class_=cls)
        if el:
            print(f"{cls}: {el.text.strip()[:200]}...")
    
    # Samples
    samples = problem_body.find_all('div', class_='sample-content')
    print(f"Sample count: {len(samples)}")
    for i, s in enumerate(samples):
        inp = s.find('pre', class_='sample-input')
        out = s.find('pre', class_='sample-output')
        if inp:
            print(f"  Sample Input #{i}: {inp.text.strip()[:100]}")
        if out:
            print(f"  Sample Output #{i}: {out.text.strip()[:100]}")
    
    # Print the full problem body HTML for inspection
    print(f"\nFull problem body HTML (first 2000 chars):")
    print(str(problem_body)[:2000])
else:
    print("No problem-body found")
    # Try to find the content
    print("HTML around '1001':")
    idx = r.text.find('1001')
    if idx >= 0:
        print(r.text[max(0,idx-500):idx+500])
    print("Available classes:", [c.get('class') for c in soup.find_all(class_=True)][:20])

# ====== 2. Login process ======
print("\n" + "=" * 60)
print("LOGIN STRUCTURE")
print("=" * 60)

s = requests.Session()
r = s.get('https://acm.ecnu.edu.cn/login/', timeout=10)
soup2 = BeautifulSoup(r.text, 'html.parser')

# Find the form
form = soup2.find('form')
if form:
    print(f"Form action: {form.get('action')}")
    inputs = form.find_all('input')
    for inp in inputs:
        name = inp.get('name')
        type_v = inp.get('type')
        value = inp.get('value', '')
        if name:
            disp_val = value[:30] if value else '(empty)'
            print(f"  Input: name={name}, type={type_v}, value={disp_val}")
    
    # Check for captcha
    captcha_img = form.find('img', class_='captcha')
    if captcha_img:
        print(f"Captcha image found: {captcha_img.get('src')}")

# ====== 3. Submit process ======
print("\n" + "=" * 60)
print("SUBMIT PAGE (requires login)")
print("=" * 60)
r2 = s.get('https://acm.ecnu.edu.cn/problem/1001/submit/', timeout=10)
print(f"Status: {r2.status_code}, Final URL: {r2.url}")

# ====== 4. DeepSeek API test ======
print("\n" + "=" * 60)
print("DEEPSEEK API TEST")
print("=" * 60)

# Test code generation
payload = {
    "model": os.environ.get("LLM_MODEL", "deepseek-flash"),
    "messages": [
        {"role": "system", "content": "You are a competitive programming helper. Write C++ code to solve the problem."},
        {"role": "user", "content": "Write a C++ program that reads two integers a and b and outputs their sum. Just give the code, no explanation."}
    ],
    "max_tokens": 500
}
headers = {
    'Authorization': 'Bearer ' + DEEPSEEK_API_KEY,
    'Content-Type': 'application/json'
}
r3 = requests.post('https://api.deepseek.com/v1/chat/completions', 
                   headers=headers, json=payload, timeout=15)
print(f"Status: {r3.status_code}")
if r3.status_code == 200:
    data = r3.json()
    code = data['choices'][0]['message']['content']
    print(f"Generated code:\n{code[:500]}")
