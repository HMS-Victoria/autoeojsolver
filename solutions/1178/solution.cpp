#include <iostream>
#include <vector>
using namespace std;

int main() {
    int T;
    cin >> T; // 读取测试用例数量
    for (int t = 0; t < T; ++t) {
        int N, M;
        cin >> N >> M;

        // dp[s] 表示用不重复的1..M中的数凑成和s的方案数
        vector<long long> dp(N + 1, 0);
        dp[0] = 1; // 空集和为0

        for (int num = 1; num <= M; ++num) {
            // 倒序更新，保证每个数只用一次
            for (int s = N; s >= num; --s) {
                dp[s] += dp[s - num];
            }
        }

        // 输出结果
        cout << "case #" << t << ":\n";
        cout << dp[N] << "\n";
    }
    return 0;
}