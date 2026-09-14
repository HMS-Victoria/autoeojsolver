#include <iostream>
#include <vector>
#include <algorithm>

using namespace std;

int main() {
    int P; // 数据集数量
    cin >> P;
    
    while (P--) {
        int dataSetNumber; // 数据集编号
        cin >> dataSetNumber;
        
        vector<int> numbers(10); // 存储10个整数
        for (int i = 0; i < 10; i++) {
            cin >> numbers[i];
        }
        
        // 对数组进行降序排序
        sort(numbers.begin(), numbers.end(), greater<int>());
        
        // 第三大的数在索引2处（0-based indexing）
        int thirdLargest = numbers[2];
        
        // 输出结果
        cout << dataSetNumber << " " << thirdLargest << endl;
    }
    
    return 0;
}