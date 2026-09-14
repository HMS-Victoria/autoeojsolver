#include <iostream>
#include <string>
#include <cmath>

using namespace std;

// 将8位二进制字符串转换为十进制整数
int binaryToDecimal(string binaryStr) {
    int decimal = 0;
    int power = 128; // 2^7
    
    for (int i = 0; i < 8; i++) {
        if (binaryStr[i] == '1') {
            decimal += power;
        }
        power /= 2;
    }
    
    return decimal;
}

// 将32位二进制IP地址转换为点分十进制格式
string convertToDottedDecimal(string ipBinary) {
    string result;
    
    // 每8位一组进行转换
    for (int i = 0; i < 4; i++) {
        // 提取8位二进制数
        string octet = ipBinary.substr(i * 8, 8);
        
        // 转换为十进制
        int decimalValue = binaryToDecimal(octet);
        
        // 添加到结果字符串
        if (i > 0) {
            result += ".";
        }
        result += to_string(decimalValue);
    }
    
    return result;
}

int main() {
    string line;
    int testCases;
    
    // 读取测试用例数量
    getline(cin, line);
    testCases = stoi(line);
    
    // 处理每个测试用例
    for (int i = 0; i < testCases; i++) {
        string ipBinary;
        getline(cin, ipBinary);
        
        // 转换并输出结果
        string dottedDecimal = convertToDottedDecimal(ipBinary);
        cout << dottedDecimal << endl;
    }
    
    return 0;
}