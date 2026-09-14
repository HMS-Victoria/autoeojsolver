#include <iostream>
#include <cstring>
#include <string>
#include <vector>
#include <algorithm>
#include <cstdlib>  // for atoll? but we use stoll from <string>

using namespace std;

// 链表节点定义（与题目一致）
typedef struct Node {
    char value[100];   // 以字符串形式存储的分数
    struct Node *next;
} NODE;

// 将字符串形式的分数解析为分子和分母
void parseFraction(const char* s, long long& num, long long& den) {
    string str(s);
    size_t pos = str.find('/');
    if (pos == string::npos) {
        // 无分母，视为分母为1
        num = stoll(str);
        den = 1;
    } else {
        num = stoll(str.substr(0, pos));
        den = stoll(str.substr(pos + 1));
    }
}

// 比较两个节点的分数大小，用于sort排序
static bool cmp(const NODE* a, const NODE* b) {
    long long num1, den1, num2, den2;
    parseFraction(a->value, num1, den1);
    parseFraction(b->value, num2, den2);
    // 交叉相乘比较数值
    long long left = num1 * den2;
    long long right = num2 * den1;
    if (left != right)
        return left < right;
    // 数值相等时，比较分子大小（分子小的在前）
    return num1 < num2;
}

// 排序函数：对链表按分数值从小到大排序，返回新头指针
NODE* SortRationalList(NODE* h) {
    if (!h || !h->next)  // 空链表或只有一个节点，无需排序
        return h;

    // 将链表节点指针存入vector，便于用sort排序
    vector<NODE*> nodes;
    NODE* cur = h;
    while (cur) {
        nodes.push_back(cur);
        cur = cur->next;
    }

    sort(nodes.begin(), nodes.end(), cmp);

    // 按排序结果重新链接节点
    for (size_t i = 0; i < nodes.size() - 1; ++i) {
        nodes[i]->next = nodes[i+1];
    }
    nodes.back()->next = nullptr;

    return nodes[0];
}

int main() {
    int T;
    cin >> T;
    for (int ti = 0; ti < T; ++ti) {
        int n;
        cin >> n;
        NODE* head = nullptr;
        NODE* tail = nullptr;
        for (int i = 0; i < n; ++i) {
            string s;
            cin >> s;
            NODE* newNode = new NODE;
            // 将string复制到char数组，确保不越界
            strncpy(newNode->value, s.c_str(), 99);
            newNode->value[99] = '\0';
            newNode->next = nullptr;
            if (head == nullptr) {
                head = newNode;
                tail = newNode;
            } else {
                tail->next = newNode;
                tail = newNode;
            }
        }

        head = SortRationalList(head);

        // 输出结果
        cout << "case #" << ti << ":" << endl;
        // 注意输出格式：每个case的第一行先输出case编号，然后换行，
        // 下一行开头有一个空格，然后输出排序后的分数（用空格隔开）
        if (head) {
            cout << " ";
            NODE* cur = head;
            while (cur) {
                cout << cur->value;
                if (cur->next)
                    cout << " ";
                cur = cur->next;
            }
        }
        cout << endl;

        // 释放链表内存
        NODE* cur = head;
        while (cur) {
            NODE* tmp = cur;
            cur = cur->next;
            delete tmp;
        }
    }
    return 0;
}