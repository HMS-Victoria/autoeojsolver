#include <iostream>
#include <vector>
#include <cmath>
#include <cstring>
using namespace std;

const int MAXN = 1000000; // n的最大值

// 素数筛法，计算每个数对应的素数个数
vector<int> prime_count(MAXN + 1, 0);
vector<bool> is_prime(MAXN + 1, true);

// 预处理：计算不大于每个数的素数个数
void precompute() {
    is_prime[0] = is_prime[1] = false;
    for (int i = 2; i <= MAXN; i++) {
        if (is_prime[i]) {
            for (int j = i * 2; j <= MAXN; j += i) {
                is_prime[j] = false;
            }
        }
    }
    
    // 计算前缀和
    int count = 0;
    for (int i = 1; i <= MAXN; i++) {
        if (is_prime[i]) count++;
        prime_count[i] = count;
    }
}

// 函数f(n)：不大于n的素数个数
long long f(long long n) {
    if (n <= 1) return 1;
    if (n > MAXN) return prime_count[MAXN]; // 安全处理，但实际n不会超过10^6
    return prime_count[n];
}

// 计算F_k(n)
long long F(long long k, long long n) {
    // 当n很小或k很大时，多次迭代会很快收敛到1或2
    // 因为f(n) <= n，且对于n>1，f(n) < n（除了n=2,3时相等）
    // 实际上，迭代几次后就会稳定在较小的值
    
    long long result = n;
    for (long long i = 0; i < k; i++) {
        result = f(result);
        // 如果结果已经很小，继续迭代也不会改变
        if (result <= 2) break;
    }
    return result;
}

int main() {
    // 预处理素数个数
    precompute();
    
    long long k, n;
    // 读取直到文件结束
    while (cin >> k >> n) {
        cout << F(k, n) << endl;
    }
    
    return 0;
}