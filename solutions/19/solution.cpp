#include <iostream>
#include <string>
#include <vector>
#include <algorithm>
#include <cstring>
using namespace std;

const int MAXN = 1005; // 最大字符串长度

int n, k;
string A, B;
int dp[MAXN][MAXN]; // dp[i][j] 表示A前i个字符和B前j个字符的最长公共单词序列长度
int lcs[MAXN][MAXN]; // lcs[i][j] 表示以A[i]和B[j]结尾的最长公共子串长度

int main() {
    ios::sync_with_stdio(false);
    cin.tie(0);
    
    while (cin >> n >> k) {
        cin >> A >> B;
        
        // 将字符串转换为1-indexed方便处理
        A = " " + A;
        B = " " + B;
        
        // 初始化dp和lcs数组
        memset(dp, 0, sizeof(dp));
        memset(lcs, 0, sizeof(lcs));
        
        // 计算lcs数组：以A[i]和B[j]结尾的最长公共子串长度
        for (int i = 1; i <= n; i++) {
            for (int j = 1; j <= n; j++) {
                if (A[i] == B[j]) {
                    lcs[i][j] = lcs[i-1][j-1] + 1;
                } else {
                    lcs[i][j] = 0;
                }
            }
        }
        
        // 动态规划求解最长公共单词序列
        for (int i = 1; i <= n; i++) {
            for (int j = 1; j <= n; j++) {
                // 不选A[i]或B[j]的情况
                dp[i][j] = max(dp[i-1][j], dp[i][j-1]);
                
                // 如果以A[i]和B[j]结尾有长度至少为k的公共子串
                if (lcs[i][j] >= k) {
                    // 尝试所有可能的子串长度
                    for (int len = k; len <= lcs[i][j]; len++) {
                        // 选择这个长度为len的公共子串作为单词
                        dp[i][j] = max(dp[i][j], dp[i-len][j-len] + 1);
                    }
                }
            }
        }
        
        cout << dp[n][n] << endl;
    }
    
    return 0;
}