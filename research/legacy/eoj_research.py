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

import requests
import re

# ====== 1. Test login page ======
s = requests.Session()
r = s.get('https://acm.ecnu.edu.cn/login/', timeout=10)
print(f"[Login Page] Status: {r.status_code}, URL: {r.url}")

# Find CSRF token
csrf_match = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', r.text)
if csrf_match:
    print(f"[Login] CSRF token: {csrf_match.group(1)[:40]}...")
else:
    print("[Login] No CSRF token found")
    # Try finding it differently
    csrf_match = re.search(r'csrfmiddlewaretoken', r.text)
    print(f"[Login] 'csrfmiddlewaretoken' in text: {bool(csrf_match)}")

# Find form fields
username_fields = re.findall(r'name="(username|login|email)"', r.text)
password_fields = re.findall(r'name="(password|passwd)"', r.text)
print(f"[Login] Username fields: {username_fields}")
print(f"[Login] Password fields: {password_fields}")

# Show form area
form_idx = r.text.find('<form')
if form_idx >= 0:
    form_end = r.text.find('</form>', form_idx)
    form_html = r.text[form_idx:form_end+7]
    print(f"[Login] Form HTML ({len(form_html)} chars):")
    print(form_html[:2000])
else:
    print("[Login] No <form> tag found")
    # Search for any input fields
    inputs = re.findall(r'<input[^>]*>', r.text)
    print(f"[Login] Input fields found: {len(inputs)}")
    for inp in inputs[:10]:
        print(f"  {inp}")

# ====== 2. Test problem page ======
r2 = s.get('https://acm.ecnu.edu.cn/problem/1001/', timeout=10)
print(f"\n[Problem 1001] Status: {r2.status_code}")

# Find statement
statement = re.search(r'<div class="problem-statement"[^>]*>([\s\S]*?)</div>\s*<!-- problem-statement -->', r2.text)
if statement:
    print(f"[Problem] Statement found ({len(statement.group(1))} chars)")
else:
    print("[Problem] No statement div found")
    # Try other patterns
    for pattern in ['problem-statement', 'statement', 'description', 'problem_Description', 'problem_description', 'section']:
        if pattern in r2.text:
            idx = r2.text.find(pattern)
            print(f"[Problem] '{pattern}' found at index {idx}")
            print(f"  Context: {r2.text[max(0,idx-50):idx+100]}")

# Find sample data
samples_input = re.findall(r'<pre[^>]*class="sample-input"[^>]*>([\s\S]*?)</pre>', r2.text)
samples_output = re.findall(r'<pre[^>]*class="sample-output"[^>]*>([\s\S]*?)</pre>', r2.text)
print(f"[Problem] Samples: {len(samples_input)} inputs, {len(samples_output)} outputs")
for i, s_in in enumerate(samples_input):
    print(f"  Input #{i}: {s_in.strip()[:80]}")
for i, s_out in enumerate(samples_output):
    print(f"  Output #{i}: {s_out.strip()[:80]}")

# ====== 3. Test submit page ======
r3 = s.get('https://acm.ecnu.edu.cn/problem/1001/submit/', timeout=10)
print(f"\n[Submit 1001] Status: {r3.status_code}, URL: {r3.url}")

if 'login' in r3.url:
    print("[Submit] Redirected to login (need authentication)")
else:
    # Find submit form
    csrf_submit = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', r3.text)
    print(f"[Submit] CSRF token: {csrf_submit.group(1)[:40] if csrf_submit else 'Not found'}")

# ====== 4. Test submission status page ======
r4 = s.get('https://acm.ecnu.edu.cn/problem/status/', timeout=10)
print(f"\n[Status] Status: {r4.status_code}")

# ====== 5. Test DeepSeek API ======
print("\n[DeepSeek] Testing API...")
headers = {
    'Authorization': 'Bearer ' + DEEPSEEK_API_KEY,
    'Content-Type': 'application/json'
}
try:
    r_ds = requests.get('https://api.deepseek.com/v1/models', headers=headers, timeout=10)
    print(f"[DeepSeek] Status: {r_ds.status_code}")
    print(f"[DeepSeek] Response: {r_ds.text[:300]}")
except Exception as e:
    print(f"[DeepSeek] Error: {e}")

# Also try chat endpoint
try:
    payload = {
        "model": os.environ.get("LLM_MODEL", "deepseek-flash"),
        "messages": [{"role": "user", "content": "Say hello"}],
        "max_tokens": 20
    }
    r_ds2 = requests.post('https://api.deepseek.com/v1/chat/completions', 
                          headers=headers, json=payload, timeout=15)
    print(f"[DeepSeek Chat] Status: {r_ds2.status_code}")
    print(f"[DeepSeek Chat] Response: {r_ds2.text[:300]}")
except Exception as e:
    print(f"[DeepSeek Chat] Error: {e}")
