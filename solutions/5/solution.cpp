#include <iostream>
#include <vector>
#include <string>
#include <algorithm>
using namespace std;

// 大数乘法（字符串表示）
string multiply(string a, string b) {
    int n = a.size(), m = b.size();
    vector<int> res(n + m, 0);
    // 逐位相乘
    for (int i = n - 1; i >= 0; i--) {
        for (int j = m - 1; j >= 0; j--) {
            int mul = (a[i] - '0') * (b[j] - '0');
            int sum = mul + res[i + j + 1];
            res[i + j + 1] = sum % 10;
            res[i + j] += sum / 10;
        }
    }
    // 去除前导零
    string result;
    for (int num : res) {
        if (!(result.empty() && num == 0))
            result.push_back(num + '0');
    }
    return result.empty() ? "0" : result;
}

// 大数加法（字符串表示）
string add(string a, string b) {
    string result;
    int i = a.size() - 1, j = b.size() - 1, carry = 0;
    while (i >= 0 || j >= 0 || carry) {
        int sum = carry;
        if (i >= 0) sum += a[i--] - '0';
        if (j >= 0) sum += b[j--] - '0';
        carry = sum / 10;
        result.push_back(sum % 10 + '0');
    }
    reverse(result.begin(), result.end());
    return result;
}

int main() {
    int n;
    while (cin >> n) {
        // dp[i][0] 表示考虑前i个数，不选第i个数的所有子集的平方和
        // dp[i][1] 表示考虑前i个数，选第i个数的所有子集的平方和
        vector<string> dp0(n + 1, "0"), dp1(n + 1, "0");
        
        // 初始化：对于n=1的情况
        dp0[1] = "1";  // 空集，乘积为1，平方和为1
        dp1[1] = "1";  // {1}，乘积为1，平方和为1
        
        for (int i = 2; i <= n; i++) {
            // 不选i：可以从i-1的不选或选转移过来
            dp0[i] = add(dp0[i-1], dp1[i-1]);
            
            // 选i：只能从i-1的不选转移过来，并且每个子集乘积要乘以i，平方后要乘以i^2
            // 即 dp1[i] = dp0[i-1] * i^2
            string i_str = to_string(i);
            string i2 = multiply(i_str, i_str);
            dp1[i] = multiply(dp0[i-1], i2);
        }
        
        // 最终结果 = 不选n + 选n
        string ans = add(dp0[n], dp1[n]);
        cout << ans << endl;
    }
    return 0;
}