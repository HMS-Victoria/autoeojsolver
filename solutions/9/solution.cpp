#include <iostream>
#include <vector>
using namespace std;

int main() {
    int m, n;
    // 读取输入，直到EOF
    while (cin >> m >> n) {
        // 创建一个m行n列的二维数组
        vector<vector<int>> grid(m, vector<int>(n));
        
        // 填充数字：按行优先顺序填充1到m*n
        // 这样可以保证右边大于左边，下边大于上边
        int num = 1;
        for (int i = 0; i < m; i++) {
            for (int j = 0; j < n; j++) {
                grid[i][j] = num++;
            }
        }
        
        // 输出结果
        for (int i = 0; i < m; i++) {
            for (int j = 0; j < n; j++) {
                if (j > 0) cout << " ";
                cout << grid[i][j];
            }
            cout << endl;
        }
    }
    return 0;
}