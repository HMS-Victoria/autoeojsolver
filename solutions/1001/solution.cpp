#include <iostream>
#include <string>
#include <algorithm>
using namespace std;

// 大数加法函数，返回两个数字字符串的和
string addBigNumbers(string a, string b) {
    string result = "";
    int carry = 0; // 进位
    int i = a.length() - 1, j = b.length() - 1;
    
    // 从最低位开始逐位相加
    while (i >= 0 || j >= 0 || carry) {
        int sum = carry;
        if (i >= 0) {
            sum += a[i] - '0'; // 将字符转换为数字
            i--;
        }
        if (j >= 0) {
            sum += b[j] - '0';
            j--;
        }
        carry = sum / 10; // 计算进位
        result += (sum % 10) + '0'; // 将当前位数字转换为字符
    }
    
    // 结果需要反转，因为我们是倒序添加的
    reverse(result.begin(), result.end());
    return result;
}

int main() {
    string a, b;
    
    // 持续读取直到EOF
    while (cin >> a >> b) {
        string sum = addBigNumbers(a, b);
        cout << sum << endl;
    }
    
    return 0;
}