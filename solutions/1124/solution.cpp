#include <iostream>
#include <vector>
#include <climits>

using namespace std;

int main() {
    int n;
    // 持续读取测试数据，直到文件结束
    while (cin >> n) {
        vector<long long> a(n);
        long long total_xor = 0, total_sum = 0;
        long long min_val = LLONG_MAX; // 初始化最小值

        for (int i = 0; i < n; ++i) {
            cin >> a[i];
            total_xor ^= a[i]; // 计算所有数的异或和
            total_sum += a[i]; // 计算所有数的和
            if (a[i] < min_val) min_val = a[i]; // 找最小值
        }

        // 只有当所有数的异或和为0时，才可能分成两组异或相等
        long long ans = 0;
        if (total_xor == 0) {
            // 最大和 = 总和 - 最小值，将最小值单独分一组，其余为另一组
            ans = total_sum - min_val;
        }
        // 如果异或和不为0，理论上无解，但题目保证有解，这里输出0（可根据需要调整）
        cout << ans << endl;
    }
    return 0;
}