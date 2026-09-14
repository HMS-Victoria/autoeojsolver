#include <iostream>
#include <string>
#include <vector>
#include <cstdio>
#include <cstdlib>
using namespace std;

// 计算 NMEA 校验和（'$' 和 '*' 之间的所有字符异或）
int calculateChecksum(const string& s, size_t start, size_t end) {
    int checksum = 0;
    for (size_t i = start; i < end; ++i) {
        checksum ^= static_cast<unsigned char>(s[i]);
    }
    return checksum;
}

// 用逗号分割字符串，返回字段列表
vector<string> splitByComma(const string& s) {
    vector<string> parts;
    size_t pos = 0, next;
    while ((next = s.find(',', pos)) != string::npos) {
        parts.push_back(s.substr(pos, next - pos));
        pos = next + 1;
    }
    parts.push_back(s.substr(pos)); // 最后一个字段
    return parts;
}

int main() {
    string line;
    string result; // 存储最终北京时间

    while (getline(cin, line)) {
        if (line == "END") break;          // 结束标志
        if (line.empty()) continue;

        // 找到 '$' 和 '*' 的位置
        size_t dollar = line.find('$');
        size_t star = line.find('*', dollar);
        if (dollar == string::npos || star == string::npos) continue;

        // 计算校验和（从 '$' 后一个字符到 '*' 前）
        int calc = calculateChecksum(line, dollar + 1, star);

        // 提取星号后的两位十六进制校验值
        string checksumStr = line.substr(star + 1, 2);
        int expected = stoi(checksumStr, nullptr, 16);
        if (calc != expected) continue;   // 校验失败，跳过

        // 提取 '$' 和 '*' 之间的字段部分（不含 $ 和 *）
        string fieldsPart = line.substr(dollar + 1, star - dollar - 1);
        vector<string> fields = splitByComma(fieldsPart);

        // 字段0：语句ID，字段1：UTC时间，字段2：状态
        if (fields.size() < 3) continue;
        if (fields[0] != "GPRMC") continue;         // 不是目标语句
        if (fields[2] != "A") continue;              // 未定位，跳过

        // 解析时间字段（hhmmss.sss 格式）
        string timeStr = fields[1];
        if (timeStr.size() < 6) continue;

        // 提取小时、分钟、秒（舍弃小数部分）
        string hhStr = timeStr.substr(0, 2);
        string mmStr = timeStr.substr(2, 2);
        string ssStr;
        size_t dotPos = timeStr.find('.');
        if (dotPos != string::npos) {
            ssStr = timeStr.substr(4, dotPos - 4);
        } else {
            ssStr = timeStr.substr(4, 2);
        }

        int hh = stoi(hhStr);
        int mm = stoi(mmStr);
        int ss = stoi(ssStr);

        // 转换为北京时间（UTC+8）
        hh = (hh + 8) % 24;

        // 格式化为 HH:MM:SS
        char buf[9];
        snprintf(buf, sizeof(buf), "%02d:%02d:%02d", hh, mm, ss);
        result = string(buf);   // 更新为最后一条有效语句的时间
    }

    cout << result << endl;
    return 0;
}