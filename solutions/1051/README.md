# 题目 1051 - 完全加括号的矩阵连乘积

## 题目大意
对单向链表中的节点按分数值从小到大排序。分数以字符串形式给出（如"5/2"或"3"），分母为1时省略。要求先比较分数值，相等时比较分子大小（分子小的排前）。返回排序后链表的头指针。

## 解题思路
排序的核心是**比较两个分数的大小**。由于分数是字符串，不能直接比较，需要先解析为分子分母，再用**交叉相乘**比较数值大小，避免浮点精度问题。值相等时再比分子。

链表排序本身有多种方式，本题为了简化代码，选择**将链表节点指针存入数组，用 `std::sort` 配合自定义比较函数**，排好序后再重新串联成链表。这样做思路清晰，编码简单，且 `n` 不大时性能足够。

## 算法分析
- **算法/数据结构**: 自定义比较函数 + `std::sort` 排序数组
- **时间复杂度**: O(N log N)，其中 N 为链表节点个数
- **空间复杂度**: O(N)（存储节点指针的 vector）

## 关键点
1. **分数解析**：注意处理字符串中可能不含 `'/'` 的情况，此时分母视为 1。
2. **避免整数溢出**：分子分母范围可达 ±1e8，交叉相乘后可能达到 1e16，要用 `long long` 存储。
3. **比较逻辑**：先判断 `num1 * den2` 与 `num2 * den1` 的大小，不等时按此排序；相等时再比较分子 `num1` 与 `num2`。
4. **输出格式**：每个 case 的第一行输出 `case #i:`，第二行以空格开头，然后输出排序后的分数（空格分隔），最后换行。注意 `case #0:` 后直接换行，不要多空格。
5. **内存管理**：题目要求释放链表内存，每个节点都是 `new` 出来的，最后要逐个 `delete`。

## 代码解析

```cpp
// 解析分数：将字符串 s 转换为分子 num 和分母 den
void parseFraction(const char* s, long long& num, long long& den) {
    string str(s);
    size_t pos = str.find('/');
    if (pos == string::npos) {
        num = stoll(str);
        den = 1;               // 没有分母则视为/1
    } else {
        num = stoll(str.substr(0, pos));
        den = stoll(str.substr(pos + 1));
    }
}

// 比较两个节点对应的分数大小
static bool cmp(const NODE* a, const NODE* b) {
    long long num1, den1, num2, den2;
    parseFraction(a->value, num1, den1);
    parseFraction(b->value, num2, den2);
    long long left = num1 * den2;
    long long right = num2 * den1;
    if (left != right)
        return left < right;          // 数值小的排在前面
    return num1 < num2;               // 数值相等时，分子小的在前
}

// 排序主函数
NODE* SortRationalList(NODE* h) {
    if (!h || !h->next) return h;     // 边界：空或单个节点
    vector<NODE*> nodes;
    NODE* cur = h;
    while (cur) {
        nodes.push_back(cur);
        cur = cur->next;
    }
    sort(nodes.begin(), nodes.end(), cmp);  // 排序指针
    // 重新链接
    for (size_t i = 0; i < nodes.size() - 1; ++i) {
        nodes[i]->next = nodes[i+1];
    }
    nodes.back()->next = nullptr;
    return nodes[0];
}
```

- `parseFraction` 使用 `string::find` 寻找 `'/'`，若不存在则分母为 1，否则截取两部分。
- 比较函数 `cmp`：注意用 `long long` 存储乘积，避免溢出；相等时比较分子，符合题目“分子小的排在前面”。
- 排序后将 `vector` 中的节点重新串联，最后 `next` 置空。
- 主函数中：先读入 n 个字符串，创建链表（尾插法），调用 `SortRationalList`，然后按格式输出，最后释放内存。