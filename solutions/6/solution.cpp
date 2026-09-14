#include <iostream>
#include <vector>
#include <algorithm>
#include <cstring>
using namespace std;

const int MAXN = 50005;

int main() {
    ios::sync_with_stdio(false);
    cin.tie(0);
    
    int k;
    cin >> k;
    
    while (k--) {
        int n;
        cin >> n;
        
        // 读取所有三角形，第一个是黑色
        // 我们需要构建三角形之间的邻接关系（通过共享对角线）
        // 以及每个三角形与多边形边的关联
        
        // 存储每个三角形三个顶点
        vector<vector<int>> triangles(n-2, vector<int>(3));
        for (int i = 0; i < n-2; i++) {
            cin >> triangles[i][0] >> triangles[i][1] >> triangles[i][2];
        }
        
        // 黑色三角形是第一个
        vector<int> black = triangles[0];
        
        // 判断黑色三角形有多少条边是多边形的边
        int edge_count = 0;
        
        // 检查边 (black[0], black[1])
        if ((black[0] + 1) % n == black[1] || (black[1] + 1) % n == black[0] ||
            (black[0] == 0 && black[1] == n-1) || (black[1] == 0 && black[0] == n-1)) {
            edge_count++;
        }
        
        // 检查边 (black[1], black[2])
        if ((black[1] + 1) % n == black[2] || (black[2] + 1) % n == black[1] ||
            (black[1] == 0 && black[2] == n-1) || (black[2] == 0 && black[1] == n-1)) {
            edge_count++;
        }
        
        // 检查边 (black[2], black[0])
        if ((black[2] + 1) % n == black[0] || (black[0] + 1) % n == black[2] ||
            (black[2] == 0 && black[0] == n-1) || (black[0] == 0 && black[2] == n-1)) {
            edge_count++;
        }
        
        // 如果黑色三角形有至少一条边是多边形的边，先手可以直接剪掉它获胜
        // 否则，我们需要分析游戏树
        // 实际上，这个游戏等价于：每次可以剪掉一个"叶子"三角形（至少有一条边是多边形边）
        // 剪掉后，相邻的三角形可能会变成新的叶子
        // 这是一个树上删叶游戏，黑色三角形是根节点
        
        // 更精确的分析：构建三角形邻接图（通过共享对角线）
        // 然后判断黑色三角形在树中的位置
        
        // 如果黑色三角形有0条边是多边形的边，则需要进一步分析
        if (edge_count == 0) {
            // 构建每个顶点所属的三角形列表
            vector<vector<int>> vertex_triangles(n);
            for (int i = 0; i < n-2; i++) {
                for (int j = 0; j < 3; j++) {
                    vertex_triangles[triangles[i][j]].push_back(i);
                }
            }
            
            // 构建三角形之间的邻接关系
            // 两个三角形共享一条对角线（即共享两个顶点）
            vector<vector<int>> tri_adj(n-2);
            for (int v = 0; v < n; v++) {
                vector<int>& tris = vertex_triangles[v];
                for (int i = 0; i < tris.size(); i++) {
                    for (int j = i+1; j < tris.size(); j++) {
                        int t1 = tris[i], t2 = tris[j];
                        // 检查这两个三角形是否共享两个顶点
                        int shared = 0;
                        for (int a = 0; a < 3; a++) {
                            for (int b = 0; b < 3; b++) {
                                if (triangles[t1][a] == triangles[t2][b]) {
                                    shared++;
                                }
                            }
                        }
                        if (shared == 2) {
                            tri_adj[t1].push_back(t2);
                            tri_adj[t2].push_back(t1);
                        }
                    }
                }
            }
            
            // 去重
            for (int i = 0; i < n-2; i++) {
                sort(tri_adj[i].begin(), tri_adj[i].end());
                tri_adj[i].erase(unique(tri_adj[i].begin(), tri_adj[i].end()), tri_adj[i].end());
            }
            
            // 计算每个三角形的度数（邻居数量）
            vector<int> degree(n-2);
            for (int i = 0; i < n-2; i++) {
                degree[i] = tri_adj[i].size();
            }
            
            // 判断黑色三角形是否在树的"内部"（即度数为0或1）
            // 如果黑色三角形度数为0（孤立），则先手必败
            // 如果黑色三角形度数为1（叶子），则先手必胜
            // 如果黑色三角形度数大于1，则需要看树的形态
            
            // 实际上，对于树上删叶游戏：
            // 如果根节点（黑色三角形）的度数为0，先手必败
            // 如果根节点的度数为1，先手必胜（直接剪掉）
            // 如果根节点的度数大于1，则先手必胜（因为可以剪掉一个叶子，迫使对手进入不利局面）
            
            // 更准确地说，这是一个"树"的删叶游戏
            // 先手必胜当且仅当根节点不是孤立点
            if (degree[0] == 0) {
                cout << "NIE\n";
            } else {
                cout << "TAK\n";
            }
        } else {
            // 黑色三角形至少有一条边是多边形的边，先手可以直接剪掉它
            cout << "TAK\n";
        }
    }
    
    return 0;
}