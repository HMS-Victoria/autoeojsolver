#include <iostream>
#include <string>
#include <vector>
#include <algorithm>
#include <sstream>
#include <unordered_map>

using namespace std;

// 判断字符串 s 是否以 prefix 开头
bool startsWith(const string& s, const string& prefix) {
    if (prefix.size() > s.size()) return false;
    return s.compare(0, prefix.size(), prefix) == 0;
}

int main() {
    ios::sync_with_stdio(false);
    cin.tie(0);

    int T;
    cin >> T;                     // 测试用例数量
    cin.ignore();                 // 忽略第一行末尾的换行符
    string line;

    while (T--) {
        int N;
        cin >> N;
        cin.ignore();             // 忽略 N 后的换行符
        unordered_map<string, int> counts;   // URL -> 访问次数

        for (int i = 0; i < N; ++i) {
            getline(cin, line);
            if (line.empty()) continue;      // 安全处理空行

            size_t space = line.find(' ');
            string op = line.substr(0, space);
            string arg = line.substr(space + 1);

            if (op == "Visit") {
                // 更新访问次数
                counts[arg]++;
            } else if (op == "Display") {
                // 收集所有以 arg 开头的 URL
                vector<pair<int, string>> vec;  // (-次数, URL)
                for (const auto& p : counts) {
                    if (startsWith(p.first, arg)) {
                        vec.emplace_back(-p.second, p.first);
                    }
                }

                // 排序：先按访问次数降序（负值升序），再按字典序升序
                sort(vec.begin(), vec.end());

                // 输出结果
                for (const auto& v : vec) {
                    cout << v.second << "\n";
                }
                // 每个 Display 输出后加一个空行（用于分隔输出）
                cout << "\n";
            }
        }
    }
    return 0;
}