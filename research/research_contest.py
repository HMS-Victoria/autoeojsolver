#!/usr/bin/env python3
"""研究 EOJ 竞赛页面结构"""
import requests
import re

s = requests.Session()
s.headers.update({'User-Agent': 'Mozilla/5.0'})
s.trust_env = False

# 1. 竞赛列表页
print("=" * 50)
print("1. 竞赛列表页")
print("=" * 50)
r = s.get('https://acm.ecnu.edu.cn/contest/', timeout=15)
print(f"Status: {r.status_code}")
print(f"Length: {len(r.text)}")

# 用 BeautifulSoup 解析
from bs4 import BeautifulSoup
soup = BeautifulSoup(r.text, 'html.parser')

# 找所有比赛链接
for a in soup.find_all('a', href=re.compile(r'/contest/\d+/')):
    href = a.get('href', '')
    text = a.get_text(strip=True)
    if text:
        print(f"比赛: {text} -> {href}")

# 获取第一个比赛的ID
contest_ids = set()
for a in soup.find_all('a', href=re.compile(r'/contest/\d+/')):
    m = re.search(r'/contest/(\d+)/', a.get('href', ''))
    if m:
        contest_ids.add(m.group(1))

if contest_ids:
    cid = sorted(contest_ids)[0]
    print(f"\n{'=' * 50}")
    print(f"2. 比赛详情页 /contest/{cid}/")
    print("=" * 50)
    r2 = s.get(f'https://acm.ecnu.edu.cn/contest/{cid}/', timeout=15)
    print(f"Status: {r2.status_code}")
    print(f"Length: {len(r2.text)}")
    
    soup2 = BeautifulSoup(r2.text, 'html.parser')
    
    # 提取比赛信息
    title = soup2.find('h1') or soup2.find('h2') or soup2.find('div', class_='title')
    if title:
        print(f"比赛标题: {title.get_text(strip=True)}")
    
    # 找题目链接
    print("\n比赛中的题目:")
    for a in soup2.find_all('a', href=re.compile(r'/contest/' + cid + r'/problem/')):
        href = a.get('href', '')
        text = a.get_text(strip=True)
        print(f"  {text} -> {href}")

    # 看提交链接
    print("\n提交链接:")
    for a in soup2.find_all('a', href=re.compile(r'/contest/' + cid + r'/problem/\d+/submit/')):
        href = a.get('href', '')
        text = a.get_text(strip=True)
        print(f"  {text} -> {href}")
    
    # 看状态页面
    print("\n状态页面:")
    for a in soup2.find_all('a', href=re.compile(r'/contest/' + cid + r'/status/')):
        href = a.get('href', '')
        text = a.get_text(strip=True)
        print(f"  {text} -> {href}")
    
    # 提取一个具体题目的ID
    problem_ids = set()
    for a in soup2.find_all('a', href=re.compile(r'/contest/' + cid + r'/problem/(\d+)/')):
        m = re.search(r'/contest/' + cid + r'/problem/(\d+)/', a.get('href', ''))
        if m:
            problem_ids.add(m.group(1))
    
    if problem_ids:
        pid = sorted(problem_ids)[0]
        print(f"\n{'=' * 50}")
        print(f"3. 比赛题目页面 /contest/{cid}/problem/{pid}/")
        print("=" * 50)
        r3 = s.get(f'https://acm.ecnu.edu.cn/contest/{cid}/problem/{pid}/', timeout=15)
        print(f"Status: {r3.status_code}")
        print(f"Length: {len(r3.text)}")
        
        soup3 = BeautifulSoup(r3.text, 'html.parser')
        title3 = soup3.find('div', class_='title')
        if title3:
            print(f"题目标题: {title3.get_text(strip=True)}")
        
        body = soup3.find('div', class_='problem-body')
        if body:
            print(f"题目内容长度: {len(body.get_text(strip=True))} 字符")
        
        # 样例
        for i, ex in enumerate(soup3.find_all('div', class_='example')):
            inp = ex.find('div', class_='input')
            out = ex.find('div', class_='output')
            if inp and out:
                si = inp.find('pre')
                so = out.find('pre')
                print(f"样例 {i+1}: input={si.get_text(strip=True)[:50] if si else 'N/A'}, output={so.get_text(strip=True)[:50] if so else 'N/A'}")
        
        # 提交表单
        submit_url = f'https://acm.ecnu.edu.cn/contest/{cid}/problem/{pid}/submit/'
        print(f"\n4. 提交页面: {submit_url}")
        r4 = s.get(submit_url, timeout=15)
        print(f"Status: {r4.status_code}")
        print(f"Length: {len(r4.text)}")
        
        # 检查是否需要登录
        if 'login' in r4.url.lower():
            print("需要登录才能访问提交页面")
        else:
            soup4 = BeautifulSoup(r4.text, 'html.parser')
            # 找表单
            forms = soup4.find_all('form')
            print(f"表单数量: {len(forms)}")
            for i, f in enumerate(forms):
                action = f.get('action', '')
                print(f"  表单{i+1}: action={action}")
                # 找出所有input
                for inp in f.find_all(['input', 'textarea', 'select']):
                    name = inp.get('name', '')
                    if name:
                        print(f"    字段: {name}")
