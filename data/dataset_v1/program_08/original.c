#include <stdio.h>
int main(void) {
    int n;
    if (scanf("%d", &n) != 1 || n <= 0) return 0;
    int first;
    if (scanf("%d", &first) != 1) return 0;
    int maximum = first;
    for (int i = 1; i < n; ++i) {
        int value;
        if (scanf("%d", &value) != 1) return 0;
        if (value > maximum) maximum = value;
    }
    printf("%d\n", maximum);
    return 0;
}
