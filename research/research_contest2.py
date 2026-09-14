#!/usr/bin/env python3
"""研究 EOJ 竞赛页面结构 v2"""
import requests, re, sys
sys.stdout.reconfigure(encoding='utf-8')
from bs4 import BeautifulSoup

s = requests.Session()
s.headers.update({'User-Agent': 'Mozilla/5.0'})
s.trust_env = False

BASE = 'https://acm.ecnu.edu.cn'

def dump(title, url, save=False):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"  URL: {url}")
    print(f"{'='*60}")
    r = s.get(url, timeout=15)
    print(f"  Status: {r.status_code}")
    print(f"  Length: {len(r.text)}")
    print(f"  Final URL: {r.url}")
    if save:
        fname = url.replace('/','_').replace(':','') + '.html'
        with open(fname, 'w', encoding='utf-8') as f:
            f.write(r.text)
        print(f"  Saved: {fname}")
    return r

# 1. 竞赛列表页 - 提取所有比赛ID和名称
print("="*60)
print("  1. 竞赛列表页")
print("="*60)
r = s.get(f'{BASE}/contest/', timeout=15)
soup = BeautifulSoup(r.text, 'html.parser')

contests = []
for a in soup.find_all('a', href=re.compile(r'^/contest/\d+/?$')):
    m = re.search(r'/contest/(\d+)/', a['href'])
    if m:
        cid = m.group(1)
        name = a.get_text(strip=True)
        if name:
            contests.append((cid, name))
            print(f"  [{cid}] {name}")

print(f"\n  共 {len(contests)} 场比赛")

# 先看一个公开比赛（contest 867）
# 再看需要登录的比赛
for cid, name in [('867', 'Contest #867'), ('1000', '天梯赛')]:
    print(f"\n{'='*60}")
    print(f"  2. 比赛详情: [{cid}] {name}")
    print(f"{'='*60}")
    
    # 详情页
    detail_url = f'{BASE}/contest/{cid}/'
    r = s.get(detail_url)
    soup = BeautifulSoup(r.text, 'html.parser')
    
    # 查找所有导航tab
    tabs = []
    for a in soup.find_all('a', class_='item'):
        href = a.get('href', '')
        text = a.get_text(strip=True)
        if text:
            tabs.append((text, href))
    print(f"  导航Tab: {tabs}")
    
    # 尝试访问子页面
    for subpath in ['problems/', 'problem/', 'status/', 'submissions/']:
        suburl = f'{BASE}/contest/{cid}/{subpath}'
        rr = s.get(suburl)
        print(f"\n  [{subpath}] Status={rr.status_code}, Len={len(rr.text)}, URL={rr.url}")
        
        # 找题目链接
        soup2 = BeautifulSoup(rr.text, 'html.parser')
        problem_links = []
        for a2 in soup2.find_all('a', href=True):
            h = a2['href']
            if re.search(r'/contest/' + cid + r'/problem/', h):
                txt = a2.get_text(strip=True)
                if txt:
                    problem_links.append((txt, h))
        
        if problem_links:
            print(f"  Found {len(problem_links)} problems:")
            for txt, h in problem_links[:10]:
                print(f"    {txt} -> {h}")
        
        # 找表格中的题目
        for table in soup2.find_all('table'):
            for tr in table.find_all('tr')[1:]:
                tds = tr.find_all('td')
                if len(tds) >= 2:
                    link = tds[0].find('a') or tds[1].find('a')
                    if link:
                        print(f"    表格行: {tds[0].get_text(strip=True)} | {tds[1].get_text(strip=True)}")

# 3. 登录后看看有哪些不一样
print(f"\n{'='*60}")
print(f"  3. 检查是否需要登录")
print(f"{'='*60}")
for path in [f'/contest/1000/problems/', f'/contest/867/problems/']:
    r = s.get(f'{BASE}{path}')
    print(f"  {path} -> {r.url}, Status={r.status_code}")
    if 'login' in r.url:
        print("    => 需要登录!")
    soup = BeautifulSoup(r.text, 'html.parser')
    for a in soup.find_all('a', href=True):
        if 'problem' in a['href']:
            print(f"    link: {a.get_text(strip=True)} -> {a['href']}")
