#include <iostream>
#include <string>
#include <cctype>   // for isdigit
using namespace std;

// 使用128位整数以避免中间结果溢出
typedef __int128 int128;

// 求最大公约数（支持负数，内部取绝对值）
int128 gcd(int128 a, int128 b) {
    a = a < 0 ? -a : a;
    b = b < 0 ? -b : b;
    while (b != 0) {
        int128 t = b;
        b = a % b;
        a = t;
    }
    return a;
}

// 将分数约分为最简形式，并确保分母为正
void reduce(int128 &num, int128 &den) {
    if (den < 0) {
        num = -num;
        den = -den;
    }
    if (num == 0) {
        den = 1;
        return;
    }
    int128 g = gcd(num, den);
    num /= g;
    den /= g;
}

// 输出 int128 类型的整数（此处仅用于最终结果，范围保证在 64 位内，但通用输出）
void printInt128(int128 x) {
    if (x == 0) {
        cout << '0';
        return;
    }
    if (x < 0) {
        cout << '-';
        x = -x;
    }
    string s;
    while (x > 0) {
        s.push_back('0' + (char)(x % 10));
        x /= 10;
    }
    for (int i = s.size() - 1; i >= 0; --i) cout << s[i];
}

int main() {
    int T;
    cin >> T;
    cin.ignore(); // 忽略 T 后面的换行

    for (int t = 0; t < T; ++t) {
        int N;
        cin >> N;            // 分数个数，本题忽略，仅按格式读入
        cin.ignore();        // 忽略 N 后面的换行

        string expr;
        getline(cin, expr);  // 读取整行表达式

        int128 total_num = 0, total_den = 1; // 累计结果初始化为 0/1
        int i = 0;
        int n = expr.length();

        // 处理开头的正负号
        int sign = 1;
        if (expr[i] == '+' || expr[i] == '-') {
            sign = (expr[i] == '-') ? -1 : 1;
            ++i;
        }

        while (i < n) {
            // 解析分子
            int128 num = 0;
            while (i < n && isdigit(expr[i])) {
                num = num * 10 + (expr[i] - '0');
                ++i;
            }
            // 跳过 '/'
            if (i < n && expr[i] == '/') ++i;

            // 解析分母
            int128 den = 0;
            while (i < n && isdigit(expr[i])) {
                den = den * 10 + (expr[i] - '0');
                ++i;
            }

            // 应用当前项的符号，并约分
            num *= sign;
            reduce(num, den);

            // 累加： total = total + current
            total_num = total_num * den + total_den * num;
            total_den = total_den * den;
            reduce(total_num, total_den);   // 每次累加后约分，防止溢出

            // 查找下一个运算符（+ 或 -）
            if (i < n && (expr[i] == '+' || expr[i] == '-')) {
                sign = (expr[i] == '-') ? -1 : 1;
                ++i;
            }
            // 若已到末尾则结束，否则忽略（输入保证合法）
        }

        // 输出结果
        cout << "case #" << t << ":\n";
        if (total_den == 1) {
            printInt128(total_num);
            cout << "\n";
        } else {
            printInt128(total_num);
            cout << '/';
            printInt128(total_den);
            cout << "\n";
        }
    }
    return 0;
}