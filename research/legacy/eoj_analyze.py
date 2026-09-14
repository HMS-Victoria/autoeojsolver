import requests
import re

r = requests.get('https://acm.ecnu.edu.cn/problem/', timeout=10,
                 headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})
text = r.text

print(f"Total length: {len(text)}")

# Find all links
for m in re.finditer(r'<a[^>]*href="([^"]+)"[^>]*>([^<]+)</a>', text):
    href = m.group(1)
    label = m.group(2).strip()
    if href and '/problem/' in href:
        print(f"  LINK: {href:40s} | {label}")

# Look for the problem table / list
print("\n=== Looking for problem list ===")
idx = text.find('1001')
print(f"1001 at idx: {idx}")
if idx >= 0:
    print(text[max(0,idx-500):idx+500])

idx2 = text.find('tbody')
print(f"\ntbody at idx: {idx2}")
if idx2 >= 0:
    print(text[idx2:idx2+2000])

# Check if page uses JavaScript rendering
if 'javascript' in text[:1000].lower():
    print("\nPage may use JavaScript")
