#include <iostream>
#include <vector>
#include <algorithm>
#include <climits>

using namespace std;

/**
 * 计算给定球数和楼层数时，最坏情况下所需的最小掉落次数
 * 使用动态规划方法
 * dp[i][j] 表示有 i 个球和 j 层楼时，最坏情况下的最小掉落次数
 */
int minDrops(int balls, int floors) {
    // 边界情况：如果没有楼层，不需要掉落
    if (floors == 0) return 0;
    // 如果只有一个球，必须逐层测试，最坏情况需要掉落 floors 次
    if (balls == 1) return floors;
    
    // 创建 DP 表，balls+1 行，floors+1 列
    vector<vector<int>> dp(balls + 1, vector<int>(floors + 1, 0));
    
    // 初始化：当只有 1 个球时，需要逐层测试
    for (int j = 1; j <= floors; j++) {
        dp[1][j] = j;
    }
    
    // 初始化：当只有 1 层楼时，只需要 1 次掉落
    for (int i = 1; i <= balls; i++) {
        dp[i][1] = 1;
    }
    
    // 填充 DP 表
    for (int i = 2; i <= balls; i++) {           // 遍历球数
        for (int j = 2; j <= floors; j++) {      // 遍历楼层数
            dp[i][j] = INT_MAX;                  // 初始化为最大值
            // 尝试从每一层 k 开始掉落第一个球
            for (int k = 1; k <= j; k++) {
                // 如果球在第 k 层碎了，则问题变为 i-1 个球，k-1 层楼
                // 如果球没碎，则问题变为 i 个球，j-k 层楼
                // 取两种情况的最大值，再加 1（当前这次掉落）
                int worst = 1 + max(dp[i-1][k-1], dp[i][j-k]);
                // 取所有 k 中的最小值
                dp[i][j] = min(dp[i][j], worst);
            }
        }
    }
    
    return dp[balls][floors];
}

int main() {
    int P;
    cin >> P;  // 读取数据组数
    
    while (P--) {
        int problemNum, balls, floors;
        cin >> problemNum >> balls >> floors;
        
        // 计算结果并输出
        int result = minDrops(balls, floors);
        cout << problemNum << " " << result << endl;
    }
    
    return 0;
}