#include <stdio.h>
int main(void) {
    int n;
    if (scanf("%d", &n) != 1 || n < 0) return 0;
    int positives = 0;
    for (int i = 0; i < n; ++i) {
        int x;
        if (scanf("%d", &x) != 1) return 0;
        if (x > 0) ++positives;
    }
    printf("%d\n", positives);
    return 0;
}
