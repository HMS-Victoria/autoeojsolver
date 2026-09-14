#include <iostream>
#include <string>
#include <stack>
#include <cctype>

using namespace std;

// 定义运算符优先级
int precedence(char op) {
    if (op == '!') return 3;  // 非运算优先级最高
    if (op == '&') return 2;  // 与运算
    if (op == '|') return 1;  // 或运算优先级最低
    return 0;
}

// 应用运算符进行计算
bool applyOp(bool a, bool b, char op) {
    switch (op) {
        case '&': return a && b;
        case '|': return a || b;
        default: return false;
    }
}

// 应用非运算符
bool applyNot(bool a) {
    return !a;
}

// 将字符转换为布尔值
bool charToBool(char c) {
    return c == 'V';
}

// 计算布尔表达式的主函数
bool evaluateExpression(const string& expr) {
    stack<bool> values;   // 操作数栈
    stack<char> ops;      // 运算符栈
    
    for (size_t i = 0; i < expr.length(); i++) {
        // 跳过空格
        if (expr[i] == ' ') continue;
        
        // 如果是操作数（V或F）
        if (expr[i] == 'V' || expr[i] == 'F') {
            values.push(charToBool(expr[i]));
        }
        // 左括号
        else if (expr[i] == '(') {
            ops.push(expr[i]);
        }
        // 右括号
        else if (expr[i] == ')') {
            while (!ops.empty() && ops.top() != '(') {
                char op = ops.top();
                ops.pop();
                
                if (op == '!') {
                    bool val = values.top();
                    values.pop();
                    values.push(applyNot(val));
                } else {
                    bool b = values.top(); values.pop();
                    bool a = values.top(); values.pop();
                    values.push(applyOp(a, b, op));
                }
            }
            if (!ops.empty()) ops.pop(); // 弹出左括号
        }
        // 运算符
        else if (expr[i] == '!' || expr[i] == '&' || expr[i] == '|') {
            // 处理优先级：当前运算符优先级低于栈顶运算符时，先计算栈顶
            while (!ops.empty() && ops.top() != '(' && 
                   precedence(ops.top()) >= precedence(expr[i])) {
                char op = ops.top();
                ops.pop();
                
                if (op == '!') {
                    bool val = values.top();
                    values.pop();
                    values.push(applyNot(val));
                } else {
                    bool b = values.top(); values.pop();
                    bool a = values.top(); values.pop();
                    values.push(applyOp(a, b, op));
                }
            }
            ops.push(expr[i]);
        }
    }
    
    // 处理剩余的运算符
    while (!ops.empty()) {
        char op = ops.top();
        ops.pop();
        
        if (op == '!') {
            bool val = values.top();
            values.pop();
            values.push(applyNot(val));
        } else {
            bool b = values.top(); values.pop();
            bool a = values.top(); values.pop();
            values.push(applyOp(a, b, op));
        }
    }
    
    return values.top();
}

int main() {
    string line;
    int caseNum = 1;
    
    // 读取直到EOF
    while (getline(cin, line)) {
        // 跳过空行
        if (line.empty()) continue;
        
        bool result = evaluateExpression(line);
        cout << "Expression " << caseNum << ": " << (result ? 'V' : 'F') << endl;
        caseNum++;
    }
    
    return 0;
}