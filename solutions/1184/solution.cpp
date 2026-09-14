#include <iostream>
#include <vector>
#include <algorithm>
#include <cmath>
#include <iomanip>
using namespace std;

// 计算两点间的欧氏距离
double distance(const pair<double, double>& a, const pair<double, double>& b) {
    double dx = a.first - b.first;
    double dy = a.second - b.second;
    return sqrt(dx * dx + dy * dy);
}

int main() {
    // 设置输出精度
    cout << fixed << setprecision(5);
    int n;
    while (cin >> n) {
        vector<pair<double, double>> points(n);
        for (int i = 0; i < n; ++i) {
            cin >> points[i].first >> points[i].second;
        }
        // 按 x 坐标排序，如果 x 相同则按 y 排序（保证顺序）
        sort(points.begin(), points.end());
        
        // 处理 n=1 的边界情况
        if (n == 1) {
            cout << "0.00000\n";
            continue;
        }
        
        // 预计算所有点对间距离
        vector<vector<double>> dist(n, vector<double>(n, 0.0));
        for (int i = 0; i < n; ++i) {
            for (int j = i + 1; j < n; ++j) {
                dist[i][j] = distance(points[i], points[j]);
            }
        }
        
        // dp[i][j] 表示从点0出发，一条路径到达 i，另一条到达 j（i < j），覆盖了所有 0..j 的点
        vector<vector<double>> dp(n, vector<double>(n, 1e100));
        dp[0][1] = dist[0][1];  // 初始两条路径分别到点0和点1
        
        for (int j = 2; j < n; ++j) {
            // 情况1: i < j-1，路径从 j-1 扩展到 j
            for (int i = 0; i < j - 1; ++i) {
                dp[i][j] = dp[i][j-1] + dist[j-1][j];
            }
            // 情况2: i == j-1，需要从前面的某个点 k 飞过来
            double best = 1e100;
            for (int k = 0; k < j - 1; ++k) {
                best = min(best, dp[k][j-1] + dist[k][j]);
            }
            dp[j-1][j] = best;
        }
        
        // 最终答案：从点 n-2 和 n-1 返回起点（点 n-1）
        double ans = dp[n-2][n-1] + dist[n-2][n-1];
        cout << ans << "\n";
    }
    return 0;
}