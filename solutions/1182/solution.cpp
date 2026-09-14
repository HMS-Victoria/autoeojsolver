#include <iostream>
#include <vector>
#include <climits>
using namespace std;

int main() {
    int M, n;
    // 循环读取每个测试用例，直到 EOF
    while (cin >> M >> n) {
        vector<long long> l(n);
        for (int i = 0; i < n; ++i) {
            cin >> l[i];
        }

        // 前缀和
        vector<long long> prefix(n + 1, 0);
        for (int i = 0; i < n; ++i) {
            prefix[i + 1] = prefix[i] + l[i];
        }

        // dp[i] 表示前 i 个单词的最小代价（最后一行不计入）
        vector<long long> dp(n + 1, LLONG_MAX / 2);
        dp[0] = 0;

        for (int i = 1; i <= n; ++i) {
            // 尝试将 [j+1, i] 作为最后一行（或当前行）
            for (int j = 0; j < i; ++j) {
                long long sum = prefix[i] - prefix[j];               // 单词总长度
                long long spaces = M - (i - j - 1) - sum;           // 额外空格数
                if (spaces >= 0) {                                  // 可以放在一行
                    if (i == n) {
                        // 最后一行不计入代价
                        dp[i] = min(dp[i], dp[j]);
                    } else {
                        long long cost = spaces * spaces * spaces;  // 立方
                        dp[i] = min(dp[i], dp[j] + cost);
                    }
                }
            }
        }

        cout << dp[n] << endl;
    }
    return 0;
}