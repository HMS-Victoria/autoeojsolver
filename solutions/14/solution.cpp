#include <iostream>
#include <string>
#include <vector>
#include <algorithm>
#include <cmath>
using namespace std;

typedef unsigned long long ULL;
const int BASE = 131; // 哈希基数

// 计算字符串哈希值
vector<ULL> getHash(const string& s) {
    int n = s.size();
    vector<ULL> h(n+1, 0);
    for (int i = 0; i < n; i++) {
        h[i+1] = h[i] * BASE + s[i];
    }
    return h;
}

// 预计算BASE的幂次
vector<ULL> getPow(int n) {
    vector<ULL> p(n+1, 1);
    for (int i = 1; i <= n; i++) {
        p[i] = p[i-1] * BASE;
    }
    return p;
}

// 获取子串哈希，使用预计算的幂次
ULL getSubHash(const vector<ULL>& h, int l, int r, const vector<ULL>& p) {
    // l, r 是闭区间 [l, r]
    return h[r+1] - h[l] * p[r-l+1];
}

int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);
    
    string s1, s2;
    // 读取两行，每行可能包含长度前缀（如 "12 AGCGCGATTTTT"）
    while (getline(cin, s1) && getline(cin, s2)) {
        // 提取字符串部分（去掉前面的数字和空格）
        auto extract = [](string& s) -> string {
            size_t pos = s.find(' ');
            if (pos != string::npos) {
                return s.substr(pos+1);
            }
            return s;
        };
        
        string str1 = extract(s1);
        string str2 = extract(s2);
        
        int n = str1.size(), m = str2.size();
        
        // 预处理哈希和幂次
        vector<ULL> h1 = getHash(str1);
        vector<ULL> h2 = getHash(str2);
        vector<ULL> p1 = getPow(n);
        vector<ULL> p2 = getPow(m);
        
        // 预处理反转字符串的哈希（用于判断回文）
        string rev1 = str1;
        string rev2 = str2;
        reverse(rev1.begin(), rev1.end());
        reverse(rev2.begin(), rev2.end());
        vector<ULL> rh1 = getHash(rev1);
        vector<ULL> rh2 = getHash(rev2);
        vector<ULL> rp1 = getPow(n);
        vector<ULL> rp2 = getPow(m);
        
        int ans = 0;
        
        // 枚举所有可能的奇数长度回文中心
        for (int i = 0; i < n; i++) {
            for (int j = 0; j < m; j++) {
                // 以 str1[i] 和 str2[j] 为中心，找最长公共回文
                int lo = 0, hi = min({i, n-1-i, j, m-1-j});
                while (lo <= hi) {
                    int mid = (lo + hi) / 2;
                    int len = 2 * mid + 1;
                    
                    // 检查 str1 中 [i-mid, i+mid] 是否是回文
                    ULL h1_left = getSubHash(h1, i-mid, i+mid, p1);
                    // 反转后对应位置
                    int rev_l = n-1-(i+mid);
                    int rev_r = n-1-(i-mid);
                    ULL h1_rev = getSubHash(rh1, rev_l, rev_r, rp1);
                    
                    // 检查 str2 中 [j-mid, j+mid] 是否是回文
                    ULL h2_left = getSubHash(h2, j-mid, j+mid, p2);
                    int rev_l2 = m-1-(j+mid);
                    int rev_r2 = m-1-(j-mid);
                    ULL h2_rev = getSubHash(rh2, rev_l2, rev_r2, rp2);
                    
                    if (h1_left == h1_rev && h2_left == h2_rev && h1_left == h2_left) {
                        ans = max(ans, len);
                        lo = mid + 1;
                    } else {
                        hi = mid - 1;
                    }
                }
            }
        }
        
        cout << ans << "\n";
    }
    
    return 0;
}