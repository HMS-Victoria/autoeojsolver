#include <iostream>
#include <vector>
#include <algorithm>
#include <climits>
using namespace std;

typedef long long ll;

int main() {
    int n; // 小镇数量
    ll S, x; // 初始体力，每只鸡恢复的体力
    
    // 循环读取多个测试用例，直到EOF
    while (cin >> n >> S >> x) {
        vector<ll> w(n); // 消耗的体力
        vector<ll> P(n); // 每个小镇鸡的价格
        
        // 读取消耗体力
        for (int i = 0; i < n; i++) {
            cin >> w[i];
        }
        
        // 读取价格
        for (int i = 0; i < n; i++) {
            cin >> P[i];
        }
        
        // 贪心策略：维护一个单调递增的价格队列（按价格排序）
        // 当需要买鸡时，从最便宜的开始买
        vector<pair<ll, int>> cheap; // (价格, 小镇编号)
        ll cur_energy = S; // 当前体力
        ll total_cost = 0; // 总花费
        bool possible = true; // 是否可能完成
        
        // 遍历每个路段
        for (int i = 0; i < n; i++) {
            // 到达小镇i，可以在这里买鸡，将当前小镇加入候选
            cheap.push_back({P[i], i});
            
            // 按价格排序，保持最便宜的在前
            sort(cheap.begin(), cheap.end());
            
            // 如果当前体力不足以走下一段路
            while (cur_energy < w[i]) {
                if (cheap.empty()) {
                    possible = false;
                    break;
                }
                
                // 买最便宜的鸡
                ll price = cheap[0].first;
                cur_energy += x;
                total_cost += price;
                
                // 移除已购买的鸡（每个小镇只能买一次）
                cheap.erase(cheap.begin());
            }
            
            if (!possible) break;
            
            // 消耗体力走这段路
            cur_energy -= w[i];
        }
        
        if (!possible) {
            cout << -1 << endl;
        } else {
            cout << total_cost << endl;
        }
    }
    
    return 0;
}