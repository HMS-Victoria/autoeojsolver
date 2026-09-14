#include <iostream>
#include <vector>
#include <algorithm>
#include <cmath>
#include <cstring>
using namespace std;

const int MAXN = 105; // 最大人数

struct Point {
    int x, y;
};

int n, r;
Point men[MAXN], women[MAXN];
int match[MAXN]; // 记录姐姐匹配的叔叔编号
bool vis[MAXN];  // 访问标记
vector<int> g[MAXN]; // 邻接表

// 计算两点之间的欧几里得距离
double dist(Point a, Point b) {
    return sqrt((a.x - b.x) * (a.x - b.x) + (a.y - b.y) * (a.y - b.y));
}

// 匈牙利算法寻找增广路
bool dfs(int u) {
    for (int v : g[u]) {
        if (!vis[v]) {
            vis[v] = true;
            if (match[v] == -1 || dfs(match[v])) {
                match[v] = u;
                return true;
            }
        }
    }
    return false;
}

// 计算当前距离限制下能匹配的最大对数
int maxMatch() {
    memset(match, -1, sizeof(match));
    int res = 0;
    for (int i = 0; i < n; i++) {
        memset(vis, false, sizeof(vis));
        if (dfs(i)) res++;
    }
    return res;
}

int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);
    
    // 处理多组测试数据直到EOF
    while (cin >> n >> r) {
        // 读入n位叔叔的位置
        for (int i = 0; i < n; i++) {
            cin >> men[i].x >> men[i].y;
        }
        // 读入n位姐姐的位置
        for (int i = 0; i < n; i++) {
            cin >> women[i].x >> women[i].y;
        }
        
        // 构建二分图：叔叔在左，姐姐在右
        // 如果距离不超过r，则连边
        for (int i = 0; i < n; i++) {
            g[i].clear();
            for (int j = 0; j < n; j++) {
                if (dist(men[i], women[j]) <= r + 1e-9) { // 加上小误差避免浮点精度问题
                    g[i].push_back(j);
                }
            }
        }
        
        int dances = 0;
        bool canDance = true;
        
        while (canDance) {
            int matchCount = maxMatch();
            if (matchCount < n) {
                canDance = false;
                break;
            }
            
            // 完成一支舞曲，交换舞伴位置
            // 对于每对匹配的舞伴，叔叔和姐姐交换位置
            // 注意：match[i]表示姐姐i匹配的叔叔编号，我们需要正确交换位置
            vector<Point> newMen(n), newWomen(n);
            // 先复制原始位置
            for (int i = 0; i < n; i++) {
                newMen[i] = men[i];
                newWomen[i] = women[i];
            }
            
            // 交换匹配的舞伴位置
            for (int i = 0; i < n; i++) {
                if (match[i] != -1) {
                    int manIdx = match[i]; // 匹配的叔叔编号
                    int womanIdx = i;      // 当前姐姐编号
                    // 交换位置：叔叔去姐姐的位置，姐姐去叔叔的位置
                    newMen[manIdx] = women[womanIdx];
                    newWomen[womanIdx] = men[manIdx];
                }
            }
            
            // 更新位置
            for (int i = 0; i < n; i++) {
                men[i] = newMen[i];
                women[i] = newWomen[i];
            }
            
            dances++;
            
            // 重新构建图
            for (int i = 0; i < n; i++) {
                g[i].clear();
                for (int j = 0; j < n; j++) {
                    if (dist(men[i], women[j]) <= r + 1e-9) {
                        g[i].push_back(j);
                    }
                }
            }
        }
        
        cout << dances << "\n";
    }
    
    return 0;
}