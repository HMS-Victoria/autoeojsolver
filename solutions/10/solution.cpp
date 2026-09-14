#include <iostream>
#include <string>
#include <vector>
#include <algorithm>
using namespace std;

// 根据给定的n，计算F(n)的分子和分母
// 思路：从根节点(1/1)开始，根据n的二进制表示（从最高位到最低位）决定向左还是向右
// 但注意：题目中的遍历顺序是层序遍历（广度优先），而n是层序遍历的序号
// 实际上，这个序列对应的是Calkin-Wilf树，其性质是：第n个有理数可以通过n的二进制表示得到
// 具体方法：将n写成二进制，去掉最高位的1，然后从左到右扫描，遇到0表示向左，遇到1表示向右
// 从(1/1)开始，按照路径移动，最终得到F(n)
void findFraction(long long n, long long &p, long long &q) {
    p = 1, q = 1;  // 从根节点开始
    // 找到n的二进制表示的最高位
    long long highest = 1;
    while (highest <= n) {
        highest <<= 1;
    }
    highest >>= 1;  // 最高位的1
    
    // 去掉最高位，从次高位开始遍历
    long long mask = highest >> 1;
    while (mask > 0) {
        if (n & mask) {
            // 当前位是1，向右走： (p+q)/q
            p = p + q;
        } else {
            // 当前位是0，向左走： p/(p+q)
            q = p + q;
        }
        mask >>= 1;
    }
}

int main() {
    int T;
    cin >> T;
    for (int caseNum = 1; caseNum <= T; caseNum++) {
        long long n;
        cin >> n;
        long long p, q;
        findFraction(n, p, q);
        cout << "Case " << caseNum << ": " << p << "/" << q << endl;
    }
    return 0;
}