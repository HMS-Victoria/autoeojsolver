#include <iostream>
#include <vector>
#include <cstring>
#include <queue>
#include <algorithm>
using namespace std;

const int MAXN = 30; // 0-24 共25个节点，24表示汇点
const int INF = 0x3f3f3f3f;

struct Edge {
    int to, cap, rev;
};

vector<Edge> G[MAXN];
int level[MAXN], iter[MAXN];

// 添加边
void add_edge(int from, int to, int cap) {
    G[from].push_back({to, cap, (int)G[to].size()});
    G[to].push_back({from, 0, (int)G[from].size() - 1});
}

// BFS构建层次图
void bfs(int s) {
    memset(level, -1, sizeof(level));
    queue<int> q;
    level[s] = 0;
    q.push(s);
    while (!q.empty()) {
        int v = q.front(); q.pop();
        for (auto &e : G[v]) {
            if (e.cap > 0 && level[e.to] < 0) {
                level[e.to] = level[v] + 1;
                q.push(e.to);
            }
        }
    }
}

// DFS寻找增广路
int dfs(int v, int t, int f) {
    if (v == t) return f;
    for (int &i = iter[v]; i < (int)G[v].size(); i++) {
        Edge &e = G[v][i];
        if (e.cap > 0 && level[v] < level[e.to]) {
            int d = dfs(e.to, t, min(f, e.cap));
            if (d > 0) {
                e.cap -= d;
                G[e.to][e.rev].cap += d;
                return d;
            }
        }
    }
    return 0;
}

// 最大流算法
int max_flow(int s, int t) {
    int flow = 0;
    while (true) {
        bfs(s);
        if (level[t] < 0) return flow;
        memset(iter, 0, sizeof(iter));
        int f;
        while ((f = dfs(s, t, INF)) > 0) {
            flow += f;
        }
    }
}

int R[24]; // 每个时间段最少需要的收银员数量
int cnt[24]; // 每个起始时间可用的申请人数

// 检查是否可以用sum个收银员满足需求
bool check(int sum, int N) {
    // 构建网络流图
    // 节点0-23: 每个小时起始的收银员数量
    // 节点24: 源点
    // 节点25: 汇点
    int S = 24, T = 25;
    
    // 清空图
    for (int i = 0; i < 26; i++) G[i].clear();
    
    // 源点到每个起始时间点，容量为该时间点的可用人数
    for (int i = 0; i < 24; i++) {
        add_edge(S, i, cnt[i]);
    }
    
    // 每个起始时间点到其覆盖的时间段（8小时）
    for (int i = 0; i < 24; i++) {
        for (int j = 0; j < 8; j++) {
            int t = (i + j) % 24;
            add_edge(i, t + 26, INF); // 使用26-49表示时间段节点
        }
    }
    
    // 时间段节点到汇点，容量为R[t]
    for (int i = 0; i < 24; i++) {
        add_edge(i + 26, T, R[i]);
    }
    
    // 检查最大流是否等于所有R的和
    int total_need = 0;
    for (int i = 0; i < 24; i++) total_need += R[i];
    
    return max_flow(S, T) == total_need;
}

int main() {
    int T;
    cin >> T;
    
    while (T--) {
        // 读取每个时间段最少需要的收银员数量
        for (int i = 0; i < 24; i++) {
            cin >> R[i];
        }
        
        int N;
        cin >> N;
        
        // 统计每个起始时间可用的申请人数
        memset(cnt, 0, sizeof(cnt));
        for (int i = 0; i < N; i++) {
            int t;
            cin >> t;
            cnt[t]++;
        }
        
        // 二分查找最少需要的收银员数量
        int left = 0, right = N, ans = -1;
        while (left <= right) {
            int mid = (left + right) / 2;
            if (check(mid, N)) {
                ans = mid;
                right = mid - 1;
            } else {
                left = mid + 1;
            }
        }
        
        if (ans == -1) {
            cout << "No Solution" << endl;
        } else {
            cout << ans << endl;
        }
    }
    
    return 0;
}