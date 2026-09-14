#include <iostream>
#include <vector>
using namespace std;

int main() {
    int n, m;
    while (cin >> n >> m) {
        if (n == -1 && m == -1) break;
        
        // dp[i] = number of binary strings of length i without m consecutive 1's
        vector<long long> dp(n + 1, 0);
        dp[0] = 1;  // empty string
        for (int i = 1; i <= n; ++i) {
            if (i < m) {
                // length less than m: all 2^i strings are valid
                dp[i] = 1LL << i;
            } else {
                // recurrence: dp[i] = sum_{k=1..m} dp[i-k]
                long long sum = 0;
                for (int k = 1; k <= m; ++k) {
                    sum += dp[i - k];
                }
                dp[i] = sum;
            }
        }
        long long total = 1LL << n;       // 2^n
        long long ans = total - dp[n];    // strings that DO contain m consecutive 1's
        cout << ans << endl;
    }
    return 0;
}