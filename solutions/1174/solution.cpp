#include <iostream>
#include <vector>
#include <algorithm> // for fill
using namespace std;

int main() {
    int T;
    cin >> T; // 测试用例个数
    while (T--) {
        int n, p, m, t;
        cin >> n >> p >> m >> t;
        // 如果目标位置或起始位置不合法，直接输出0
        if (p < 1 || p > n || t < 1 || t > n) {
            cout << 0 << '\n';
            continue;
        }
        // 滚动数组，dp_prev 表示上一分钟的状态，dp_curr 表示当前分钟的状态
        vector<long long> dp_prev(n + 2, 0); // 多开一位，防止越界
        vector<long long> dp_curr(n + 2, 0);
        dp_prev[p] = 1; // 初始位置方案数为1

        for (int step = 1; step <= m; ++step) {
            fill(dp_curr.begin(), dp_curr.end(), 0); // 清空当前分钟状态
            for (int i = 1; i <= n; ++i) {
                if (dp_prev[i] == 0) continue; // 剪枝：没有方案数则跳过
                // 向左移动
                if (i > 1) dp_curr[i - 1] += dp_prev[i];
                // 向右移动
                if (i < n) dp_curr[i + 1] += dp_prev[i];
            }
            swap(dp_prev, dp_curr); // 滚动
        }
        cout << dp_prev[t] << '\n'; // 输出 m 分钟后的方案数
    }
    return 0;
}