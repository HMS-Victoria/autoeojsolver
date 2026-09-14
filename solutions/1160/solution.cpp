```cpp
#include <iostream>
#include <iomanip>
#include <cmath>
using namespace std;

int main() {
    double M, N, T;
    
    // 持续读取输入直到EOF
    while (cin >> M >> N >> T) {
        // 计算时间区间长度
        double interval = N - M;
        
        // 如果等待时间大于等于整个区间，概率为1
        if (T >= interval) {
            cout << fixed << setprecision(3) << 1.000 << endl;
            continue;
        }
        
        // 如果等待时间小于等于0，概率为0
        if (T <= 0) {
            cout << fixed << setprecision(3) << 0.000 << endl;
            continue;
        }
        
        // 计算概率
        // 几何概率：在区间[M, N]内随机选一个时间点到达
        // 她会在某个时间点出现，但不会等待
        // 我们需要计算我到达的时间点与她出现的时间点之差不超过T的概率
        // 这相当于在正方形[M,N]×[M,N]中，|x-y| <= T的面积占比
        // 总面积 = interval^2
        // 满足条件的面积 = interval^2 - (interval-T)^2 = 2*interval*T - T^2
        double probability = (2 * interval * T - T * T) / (interval * interval);
        
        cout << fixed << setprecision(3) << probability << endl;
    }
    
    return 0;
}