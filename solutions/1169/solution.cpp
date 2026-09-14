#include <iostream>
#include <string>
#include <cctype>

using namespace std;

// 检查是否为合法邮箱地址
bool isValid(const string& s) {
    // 禁止包含空格
    if (s.find(' ') != string::npos) return false;
    // 必须有且仅有一个 '@'
    int atPos = -1;
    int atCount = 0;
    for (size_t i = 0; i < s.size(); ++i) {
        if (s[i] == '@') {
            ++atCount;
            atPos = i;
        }
    }
    if (atCount != 1) return false;
    // 拆分本地部分和域名部分
    string local = s.substr(0, atPos);
    string domain = s.substr(atPos + 1);
    // 本地部分不能为空
    if (local.empty()) return false;
    // 本地部分不能以 '.' 开头或结尾
    if (local[0] == '.' || local.back() == '.') return false;
    // 本地部分只能包含字母、数字、点、下划线、短横线
    for (char c : local) {
        if (!isalnum(c) && c != '.' && c != '_' && c != '-') return false;
    }
    // 检查连续点
    for (size_t i = 1; i < local.size(); ++i) {
        if (local[i] == '.' && local[i-1] == '.') return false;
    }
    // 域名部分不能为空
    if (domain.empty()) return false;
    // 域名部分必须包含至少一个 '.'
    if (domain.find('.') == string::npos) return false;
    // 域名部分不能以 '.' 开头或结尾
    if (domain[0] == '.' || domain.back() == '.') return false;
    // 域名部分只能包含字母、数字、点、短横线（不允许下划线）
    for (char c : domain) {
        if (!isalnum(c) && c != '.' && c != '-') return false;
    }
    // 检查连续点
    for (size_t i = 1; i < domain.size(); ++i) {
        if (domain[i] == '.' && domain[i-1] == '.') return false;
    }
    return true;
}

int main() {
    string line;
    // 逐行读取直到 EOF
    while (getline(cin, line)) {
        // 忽略空行（可选）
        if (line.empty()) continue;
        if (isValid(line)) {
            cout << line << endl;
        }
    }
    return 0;
}