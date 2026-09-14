#include <iostream>
#include <string>
#include <vector>
#include <algorithm>
#include <sstream>
#include <cctype>
#include <tuple>   // 添加 tuple 头文件

using namespace std;

// 大数乘法，以字符串形式返回 product
string multiply(const string& a, const string& b) {
    if (a == "0" || b == "0") return "0";
    int n = a.size(), m = b.size();
    vector<int> res(n + m, 0);
    // 逐位相乘
    for (int i = n - 1; i >= 0; --i) {
        int da = a[i] - '0';
        for (int j = m - 1; j >= 0; --j) {
            int db = b[j] - '0';
            int prod = da * db + res[i + j + 1];
            res[i + j + 1] = prod % 10;
            res[i + j] += prod / 10;
        }
    }
    // 转换为字符串，去掉前导零
    string result;
    bool leading = true;
    for (int x : res) {
        if (leading && x == 0) continue;
        leading = false;
        result.push_back(x + '0');
    }
    if (result.empty()) result = "0";
    return result;
}

// 快速幂：计算 base^exp (base 为非负整数字符串)
string pow_str(const string& base, long long exp) {
    if (exp == 0) return "1";   // 任何非零数的0次幂为1，但0^0在此未定义，按题意输出1
    if (base == "0") return "0";
    string res = "1", b = base;
    while (exp > 0) {
        if (exp & 1) res = multiply(res, b);
        b = multiply(b, b);
        exp >>= 1;
    }
    return res;
}

// 解析一行，返回 (base 绝对值字符串, base符号, n)
tuple<string, bool, long long> parse_line(const string& line) {
    istringstream iss(line);
    string token1, token2;
    iss >> token1 >> token2;
    // token1 形如 "2j" 或 "-3j"
    bool sign_negative = false;
    string num_str;
    for (char c : token1) {
        if (c == '-') {
            sign_negative = true;
        } else if (c == 'j' || c == 'J') {
            break;
        } else {
            num_str.push_back(c);
        }
    }
    if (num_str.empty()) num_str = "0"; // 只有 'j' 的情况？按题意不会出现
    long long n;
    iss.clear();
    iss.str(token2);
    iss >> n;
    return {num_str, sign_negative, n};
}

int main() {
    ios_base::sync_with_stdio(false);
    cin.tie(nullptr);
    string first_line;
    if (!getline(cin, first_line)) return 0;
    int T = stoi(first_line);   // 第一行是测试用例数
    for (int i = 0; i < T; ++i) {
        string line;
        if (!getline(cin, line)) break;
        // 处理输入行可能多余的空格
        while (line.empty()) getline(cin, line);
        auto [base_str, base_sign, n] = parse_line(line);
        // 计算 |a|^n
        string mag = pow_str(base_str, n);
        // 全局符号：如果 base 为负且 n 为奇数，则整体负
        bool overall_neg = base_sign && (n % 2 == 1);
        // j^n 的周期
        int mod4 = n % 4;
        bool real_part = (mod4 == 0 || mod4 == 2);
        bool imag_part = (mod4 == 1 || mod4 == 3);
        int sign_factor = (mod4 == 2 || mod4 == 3) ? -1 : 1; // 额外符号
        // 最终系数符号 = overall_neg * sign_factor
        int final_sign = (overall_neg ? -1 : 1) * sign_factor; // 修正为整数乘法
        string result;
        if (mag == "0") {
            result = "0";
        } else if (real_part) {
            // 实部结果
            if (final_sign == -1) result = "-";
            result += mag;
        } else { // imag_part
            if (final_sign == -1) result = "-";
            result += mag + "j";
        }
        cout << "case #" << i << ":\n" << result << "\n";
    }
    return 0;
}