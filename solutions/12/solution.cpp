#include <iostream>
#include <vector>
#include <string>
#include <algorithm>
using namespace std;

// 并查集数据结构，用于判断图的连通性
struct UnionFind {
    vector<int> parent, rank;
    
    UnionFind(int n) {
        parent.resize(n);
        rank.resize(n, 0);
        for (int i = 0; i < n; i++) {
            parent[i] = i;
        }
    }
    
    int find(int x) {
        if (parent[x] != x) {
            parent[x] = find(parent[x]);
        }
        return parent[x];
    }
    
    void unite(int x, int y) {
        int px = find(x), py = find(y);
        if (px == py) return;
        if (rank[px] < rank[py]) {
            parent[px] = py;
        } else if (rank[px] > rank[py]) {
            parent[py] = px;
        } else {
            parent[py] = px;
            rank[px]++;
        }
    }
    
    bool same(int x, int y) {
        return find(x) == find(y);
    }
};

// 判断是否可以通过操作使图变为完全图
// 关键观察：每次操作相当于翻转一个顶点的所有邻接边
// 最终目标是完全图，即每个顶点的度数都为N-1
// 可以证明：当且仅当初始图的补图是二分图时，可以达到目标
bool canBecomeComplete(int N, vector<pair<int,int>>& edges) {
    if (N <= 2) return true; // 0,1,2个顶点总是可以的
    
    // 构建邻接矩阵（原图）
    vector<vector<bool>> adj(N, vector<bool>(N, false));
    for (auto& e : edges) {
        int u = e.first - 1, v = e.second - 1; // 转换为0-based索引
        adj[u][v] = adj[v][u] = true;
    }
    
    // 构建补图的邻接表
    vector<vector<int>> complement(N);
    for (int i = 0; i < N; i++) {
        for (int j = i + 1; j < N; j++) {
            if (!adj[i][j]) {
                complement[i].push_back(j);
                complement[j].push_back(i);
            }
        }
    }
    
    // 检查补图是否是二分图（使用BFS染色法）
    vector<int> color(N, -1); // -1:未染色, 0:白色, 1:黑色
    bool isBipartite = true;
    
    for (int start = 0; start < N && isBipartite; start++) {
        if (color[start] != -1) continue;
        
        // BFS染色
        vector<int> queue;
        queue.push_back(start);
        color[start] = 0;
        
        for (int idx = 0; idx < (int)queue.size() && isBipartite; idx++) {
            int u = queue[idx];
            for (int v : complement[u]) {
                if (color[v] == -1) {
                    color[v] = 1 - color[u];
                    queue.push_back(v);
                } else if (color[v] == color[u]) {
                    isBipartite = false;
                    break;
                }
            }
        }
    }
    
    // 如果补图是二分图，则可以通过操作变为完全图
    if (isBipartite) return true;
    
    // 如果不是二分图，检查是否已经是完全图
    // 完全图的条件：每个顶点的度数都是N-1
    for (int i = 0; i < N; i++) {
        if ((int)complement[i].size() != 0) { // 补图中没有边才是完全图
            return false;
        }
    }
    return true;
}

int main() {
    int K;
    cin >> K;
    
    for (int caseNum = 1; caseNum <= K; caseNum++) {
        int N;
        cin >> N;
        
        int M;
        cin >> M;
        
        vector<pair<int,int>> edges;
        for (int i = 0; i < M; i++) {
            int u, v;
            cin >> u >> v;
            edges.push_back({u, v});
        }
        
        bool result = canBecomeComplete(N, edges);
        cout << "Case " << caseNum << ": " << (result ? "YES" : "NO") << endl;
    }
    
    return 0;
}