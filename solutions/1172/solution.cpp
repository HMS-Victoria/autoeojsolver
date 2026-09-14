#include <iostream>
#include <vector>
#include <algorithm>
#include <climits>

using namespace std;

int main() {
    int T;
    // 读取测试用例个数，到文件尾结束
    while (cin >> T) {
        for (int t = 0; t < T; ++t) {
            int n;  // 矩阵个数
            cin >> n;

            // 读取 n 行，每行两个数字：矩阵 Ai 的行数和列数
            vector<long long> p;  // 存储所有维数，长度为 n+1
            for (int i = 0; i < n; ++i) {
                long long a, b;
                cin >> a >> b;
                if (i == 0) {
                    p.push_back(a);  // 第一个矩阵的行数
                }
                p.push_back(b);      // 每个矩阵的列数
            }
            // 此时 p[0..n] 共 n+1 个数

            // 处理 n=1 的特例
            if (n == 1) {
                cout << 0 << endl;
                continue;
            }

            // dp[i][j] 表示 矩阵 i 到 j 的最小乘法次数 (1-indexed)
            vector<vector<long long>> dp(n + 1, vector<long long>(n + 1, 0));

            // 区间长度从 2 到 n
            for (int len = 2; len <= n; ++len) {
                for (int i = 1; i <= n - len + 1; ++i) {
                    int j = i + len - 1;
                    dp[i][j] = LLONG_MAX;  // 初始化为极大值
                    for (int k = i; k < j; ++k) {
                        // 乘法次数 = 左半 + 右半 + 合并代价
                        long long cost = dp[i][k] + dp[k + 1][j] +
                                         p[i - 1] * p[k] * p[j];
                        if (cost < dp[i][j]) {
                            dp[i][j] = cost;
                        }
                    }
                }
            }

            // 输出 dp[1][n]
            cout << dp[1][n] << endl;
        }
    }
    return 0;
}