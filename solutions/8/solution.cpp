#include <iostream>
#include <string>
#include <vector>
using namespace std;

int main() {
    int n;
    // 读取输入，直到EOF
    while (cin >> n) {
        // 如果n为0或负数，直接输出空行（根据题目要求，这里假设n>0）
        if (n <= 0) {
            cout << endl;
            continue;
        }
        
        // 特殊情况：n=1时，输出"1"
        if (n == 1) {
            cout << "1" << endl;
            continue;
        }
        
        // 使用字符串来存储斐波那契数列的拼接结果
        string result = "11";  // 前两个数：1, 1
        long long a = 1, b = 1;  // 当前的两个斐波那契数
        
        // 当结果长度小于n时，继续生成下一个斐波那契数
        while (result.length() < n) {
            long long c = a + b;  // 计算下一个斐波那契数
            string numStr = to_string(c);  // 转换为字符串
            result += numStr;  // 拼接到结果中
            a = b;
            b = c;
        }
        
        // 输出前n个字符
        cout << result.substr(0, n) << endl;
    }
    return 0;
}