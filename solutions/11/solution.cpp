#include <iostream>
#include <string>
using namespace std;

int main() {
    string s;
    // 循环读取每一行输入，直到文件结束
    while (getline(cin, s)) {
        // 目标字符串 "abcdefghijklmnopqrstuvwxyz"
        string target = "abcdefghijklmnopqrstuvwxyz";
        int i = 0, j = 0;
        // 双指针遍历：i指向目标字符串，j指向输入字符串
        while (i < 26 && j < s.length()) {
            if (s[j] == target[i]) {
                i++; // 匹配成功，目标指针前进
            }
            j++; // 输入指针始终前进
        }
        // 需要插入的字符数 = 26 - 已经匹配的字符数
        int ans = 26 - i;
        cout << ans << endl;
    }
    return 0;
}