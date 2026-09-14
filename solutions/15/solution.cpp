#include <iostream>
#include <vector>
#include <algorithm>
#include <climits>
#include <cstring>
using namespace std;

typedef long long ll;

int main() {
    ios::sync_with_stdio(false);
    cin.tie(0);
    
    int N;
    while (cin >> N) {
        vector<ll> a(N), b(N);
        for (int i = 0; i < N; i++) cin >> a[i];
        for (int i = 0; i < N; i++) cin >> b[i];
        
        // 排序：a升序，b降序（或反之），这是贪心配对的关键
        sort(a.begin(), a.end());
        sort(b.begin(), b.end(), greater<ll>());
        
        ll ans = 0;
        for (int i = 0; i < N; i++) {
            ll sum = a[i] + b[i];
            ans += sum * sum;
        }
        
        cout << ans << "\n";
    }
    
    return 0;
}