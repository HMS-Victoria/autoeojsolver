#include <iostream>
#include <string>
#include <vector>
using namespace std;

struct Toy {
    int direction; // 0: 朝内, 1: 朝外
    string job;
};

int main() {
    int n, m;
    cin >> n >> m;
    
    vector<Toy> toys(n);
    for (int i = 0; i < n; i++) {
        cin >> toys[i].direction >> toys[i].job;
    }
    
    int current = 0; // 从第一个玩具小人开始
    
    for (int i = 0; i < m; i++) {
        int a, s; // a: 0表示左数, 1表示右数; s: 步数
        cin >> a >> s;
        
        // 根据当前玩具小人的朝向和指令方向确定移动方向
        // 关键修正：朝内(0)时，左数=逆时针(-1)，右数=顺时针(+1)
        // 朝外(1)时，左数=顺时针(+1)，右数=逆时针(-1)
        int move;
        if (toys[current].direction == 0) { // 朝内
            if (a == 0) move = -1;      // 左数 = 逆时针
            else move = 1;              // 右数 = 顺时针
        } else { // 朝外
            if (a == 0) move = 1;       // 左数 = 顺时针
            else move = -1;             // 右数 = 逆时针
        }
        
        // 计算新位置，处理循环
        // 注意：左数第s个，需要移动s步
        current = (current + move * s) % n;
        if (current < 0) current += n;
    }
    
    cout << toys[current].job << endl;
    
    return 0;
}