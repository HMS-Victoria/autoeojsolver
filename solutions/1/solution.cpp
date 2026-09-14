#include <iostream>
using namespace std;

int main() {
    long long a, b;  // 使用 long long 防止溢出
    // 持续读取输入直到文件结束
    while (cin >> a >> b) {
        cout << a + b << endl;  // 输出两数之和
    }
    return 0;
}