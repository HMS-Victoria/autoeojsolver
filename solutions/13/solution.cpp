#include <iostream>
#include <string>
#include <vector>
#include <algorithm>
#include <cstring>

using namespace std;

// 6x6的格子，每个格子可能有一个或两个数字
struct Cell {
    int val1;  // 第一个数字（或斜杠左边），0表示未填
    int val2;  // 第二个数字（或斜杠右边），0表示没有第二个数字
    bool hasTwo; // 是否有两个数字
};

Cell board[6][6];
bool rowUsed[6][10]; // rowUsed[r][v] 表示第r行数字v是否被使用
bool colUsed[6][10]; // colUsed[c][v] 表示第c列数字v是否被使用
bool blockUsed[6][10]; // blockUsed[b][v] 表示第b个3x2区域数字v是否被使用

// 获取3x2区域的编号 (0-5)
int getBlock(int r, int c) {
    // 3行一组，2列一组
    return (r / 3) * 2 + (c / 2);
}

// 检查是否可以放置数字
bool canPlace(int r, int c, int v) {
    if (rowUsed[r][v] || colUsed[c][v] || blockUsed[getBlock(r, c)][v])
        return false;
    return true;
}

// 放置数字
void place(int r, int c, int v) {
    rowUsed[r][v] = true;
    colUsed[c][v] = true;
    blockUsed[getBlock(r, c)][v] = true;
}

// 移除数字
void remove(int r, int c, int v) {
    rowUsed[r][v] = false;
    colUsed[c][v] = false;
    blockUsed[getBlock(r, c)][v] = false;
}

// 深度优先搜索求解
bool dfs(int r, int c) {
    if (r == 6) return true; // 所有格子填完
    
    int nr = (c == 5) ? r + 1 : r;
    int nc = (c == 5) ? 0 : c + 1;
    
    Cell& cell = board[r][c];
    
    if (cell.val1 != 0 && !cell.hasTwo) {
        // 只有一个数字，直接跳过
        return dfs(nr, nc);
    }
    
    if (cell.hasTwo) {
        // 需要填两个数字
        if (cell.val1 == 0 && cell.val2 == 0) {
            // 两个数字都未填
            for (int v1 = 1; v1 <= 9; v1++) {
                if (!canPlace(r, c, v1)) continue;
                place(r, c, v1);
                for (int v2 = v1 + 1; v2 <= 9; v2++) {
                    if (!canPlace(r, c, v2)) continue;
                    place(r, c, v2);
                    cell.val1 = v1;
                    cell.val2 = v2;
                    if (dfs(nr, nc)) return true;
                    cell.val1 = 0;
                    cell.val2 = 0;
                    remove(r, c, v2);
                }
                remove(r, c, v1);
            }
        } else if (cell.val1 == 0) {
            // 第一个数字未填，第二个已填
            for (int v1 = 1; v1 < cell.val2; v1++) {
                if (!canPlace(r, c, v1)) continue;
                place(r, c, v1);
                cell.val1 = v1;
                if (dfs(nr, nc)) return true;
                cell.val1 = 0;
                remove(r, c, v1);
            }
        } else if (cell.val2 == 0) {
            // 第二个数字未填，第一个已填
            for (int v2 = cell.val1 + 1; v2 <= 9; v2++) {
                if (!canPlace(r, c, v2)) continue;
                place(r, c, v2);
                cell.val2 = v2;
                if (dfs(nr, nc)) return true;
                cell.val2 = 0;
                remove(r, c, v2);
            }
        }
        return false;
    }
    
    // 单个数字未填的情况（横线）
    for (int v = 1; v <= 9; v++) {
        if (!canPlace(r, c, v)) continue;
        place(r, c, v);
        cell.val1 = v;
        if (dfs(nr, nc)) return true;
        cell.val1 = 0;
        remove(r, c, v);
    }
    return false;
}

// 解析输入元素
void parseElement(const string& s, int r, int c) {
    Cell& cell = board[r][c];
    cell.val1 = 0;
    cell.val2 = 0;
    cell.hasTwo = false;
    
    size_t slashPos = s.find('/');
    if (slashPos != string::npos) {
        // 有斜杠，两个数字
        cell.hasTwo = true;
        string left = s.substr(0, slashPos);
        string right = s.substr(slashPos + 1);
        
        if (left != "-") cell.val1 = stoi(left);
        if (right != "-") cell.val2 = stoi(right);
        
        // 如果已经填了数字，标记使用
        if (cell.val1 != 0) {
            place(r, c, cell.val1);
        }
        if (cell.val2 != 0) {
            place(r, c, cell.val2);
        }
    } else {
        // 没有斜杠
        if (s != "-") {
            cell.val1 = stoi(s);
            place(r, c, cell.val1);
        }
    }
}

// 输出结果
void printBoard() {
    for (int r = 0; r < 6; r++) {
        for (int c = 0; c < 6; c++) {
            Cell& cell = board[r][c];
            if (cell.hasTwo) {
                cout << cell.val1 << "/" << cell.val2;
            } else {
                cout << cell.val1;
            }
            if (c < 5) cout << " ";
        }
        cout << endl;
    }
}

int main() {
    string line;
    // 处理多组测试用例
    while (getline(cin, line)) {
        // 初始化
        memset(rowUsed, 0, sizeof(rowUsed));
        memset(colUsed, 0, sizeof(colUsed));
        memset(blockUsed, 0, sizeof(blockUsed));
        
        // 读取第一行
        vector<string> tokens;
        size_t pos = 0;
        while ((pos = line.find(' ')) != string::npos) {
            tokens.push_back(line.substr(0, pos));
            line.erase(0, pos + 1);
        }
        tokens.push_back(line);
        
        // 解析第一行
        for (int c = 0; c < 6; c++) {
            parseElement(tokens[c], 0, c);
        }
        
        // 读取剩余5行
        for (int r = 1; r < 6; r++) {
            getline(cin, line);
            tokens.clear();
            pos = 0;
            while ((pos = line.find(' ')) != string::npos) {
                tokens.push_back(line.substr(0, pos));
                line.erase(0, pos + 1);
            }
            tokens.push_back(line);
            
            for (int c = 0; c < 6; c++) {
                parseElement(tokens[c], r, c);
            }
        }
        
        // 求解
        dfs(0, 0);
        
        // 输出结果
        printBoard();
        
        // 如果还有更多测试用例，输出空行分隔
        if (cin.peek() != EOF) {
            cout << endl;
        }
    }
    
    return 0;
}