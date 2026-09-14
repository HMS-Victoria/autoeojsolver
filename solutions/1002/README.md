# 题目 1002 - IP Address

## 题目大意
将32位二进制字符串（IP地址的原始表示）转换为点分十进制格式（如 `192.168.1.1`），每8位一组转换为十进制数，用点分隔。

## 解题思路
这道题本质上是**二进制到十进制的分组转换**，没有任何算法难度，关键是理解IP地址的表示方式。

1. **分组**：32位二进制分成4组，每组8位
2. **转换**：每组8位二进制数转换为十进制数（范围0-255）
3. **拼接**：用点号连接四个十进制数

为什么这么想？因为题目描述已经明确给出了转换规则，就是按照8位一组进行二进制到十进制的转换。这种题就是**模拟题**，按照规则一步步实现即可。

## 算法分析
- **算法/数据结构**: 模拟、字符串处理
- **时间复杂度**: O(n)，n为测试用例数量，每个用例处理固定32位
- **空间复杂度**: O(1)，只使用常数额外空间

## 关键点
- **字符串截取**：使用 `substr` 按8位一组截取子串
- **二进制转十进制**：从高位到低位累加，注意权重从128开始递减
- **输出格式**：第一个数字前不加点，后续数字前加点
- **输入处理**：第一行是测试用例数量，后续每行一个32位二进制串

## 代码解析

### 二进制转十进制函数
```cpp
int binaryToDecimal(string binaryStr) {
    int decimal = 0;
    int power = 128; // 2^7，从最高位开始
    for (int i = 0; i < 8; i++) {
        if (binaryStr[i] == '1') {
            decimal += power;
        }
        power /= 2; // 权重递减：128→64→32→...→1
    }
    return decimal;
}
```
这里用了一个小技巧：不用每次都计算2的幂，而是从128开始每次除以2，效率更高。

### 主转换函数
```cpp
string convertToDottedDecimal(string ipBinary) {
    string result;
    for (int i = 0; i < 4; i++) {
        string octet = ipBinary.substr(i * 8, 8); // 截取第i组8位
        int decimalValue = binaryToDecimal(octet);
        if (i > 0) result += "."; // 第一个数前不加点
        result += to_string(decimalValue);
    }
    return result;
}
```
注意 `substr` 的用法：`substr(起始位置, 长度)`，这里起始位置是 `i*8`，长度固定为8。

### 主函数
```cpp
int main() {
    getline(cin, line);
    testCases = stoi(line);
    for (int i = 0; i < testCases; i++) {
        getline(cin, ipBinary);
        cout << convertToDottedDecimal(ipBinary) << endl;
    }
}
```
使用 `getline` 读取整行，避免空格问题。注意 `stoi` 将字符串转为整数。