#include <iostream>
#include <string>
#include <vector>
#include <sstream>
#include <algorithm>
#include <map>
#include <cmath>

using namespace std;

// 解析多项式字符串，返回系数映射（指数 -> 系数）
map<int, long long> parsePolynomial(const string& poly) {
    map<int, long long> coeffs;
    string s = poly;
    
    // 处理特殊情况：只有常数项
    if (s.find('x') == string::npos) {
        coeffs[0] = stoll(s);
        return coeffs;
    }
    
    // 添加+号便于统一处理
    if (s[0] != '+' && s[0] != '-') {
        s = "+" + s;
    }
    
    size_t i = 0;
    while (i < s.length()) {
        // 确定符号
        int sign = 1;
        if (s[i] == '+') sign = 1;
        else if (s[i] == '-') sign = -1;
        i++;
        
        // 解析系数
        long long coeff = 0;
        bool hasCoeff = false;
        while (i < s.length() && isdigit(s[i])) {
            coeff = coeff * 10 + (s[i] - '0');
            hasCoeff = true;
            i++;
        }
        if (!hasCoeff) coeff = 1; // 没有系数默认为1
        
        // 解析指数
        int exp = 0;
        if (i < s.length() && s[i] == 'x') {
            i++;
            if (i < s.length() && s[i] == '^') {
                i++;
                while (i < s.length() && isdigit(s[i])) {
                    exp = exp * 10 + (s[i] - '0');
                    i++;
                }
            } else {
                exp = 1; // x的指数为1
            }
        } else {
            exp = 0; // 常数项
        }
        
        coeffs[exp] += sign * coeff;
    }
    
    return coeffs;
}

int main() {
    string line;
    while (getline(cin, line)) {
        if (line.empty()) continue;
        
        // 分割两个多项式
        size_t spacePos = line.find(' ');
        string poly1 = line.substr(0, spacePos);
        string poly2 = line.substr(spacePos + 1);
        
        // 解析两个多项式
        map<int, long long> coeffs1 = parsePolynomial(poly1);
        map<int, long long> coeffs2 = parsePolynomial(poly2);
        
        // 计算乘积
        map<int, long long> result; // 指数 -> 系数
        for (auto& p1 : coeffs1) {
            for (auto& p2 : coeffs2) {
                int exp = p1.first + p2.first;
                long long coeff = p1.second * p2.second;
                result[exp] += coeff;
            }
        }
        
        // 输出结果（从高次到低次，只输出非零系数）
        bool first = true;
        for (auto it = result.rbegin(); it != result.rend(); ++it) {
            if (it->second != 0) {
                if (!first) cout << " ";
                cout << it->second;
                first = false;
            }
        }
        cout << endl;
    }
    
    return 0;
}