import requests
import re

# Get problem page 1001, inspect its full structure
r = requests.get('https://acm.ecnu.edu.cn/problem/1001/', timeout=10)
text = r.text

# Find all div classes
classes = set(re.findall(r'class="([^"]*)"', text))
print("=== All CSS classes ===")
for c in sorted(classes):
    print(f"  .{c}")

# Find all sections/content areas
print("\n=== Looking for content ===")
# Find the main content container
idx = text.find('ui container')
if idx >= 0:
    print(f"ui container at {idx}: {text[idx:idx+100]}")

# Find article/content divs
for tag in ['article', 'section', 'main', 'content']:
    if tag in text:
        idx = text.find(f'<{tag}')
        if idx >= 0:
            end = text.find('>', idx)
            print(f"<{tag}> at {idx}: {text[idx:end+1][:150]}")

# Find anything after the table/navbar - the actual problem content
idx = text.find('<!--')
print(f"\n=== Comments ===")
for m in re.finditer(r'<!--(.*?)-->', text):
    c = m.group(1).strip()
    if c:
        print(f"  <!-- {c[:80]} -->")
