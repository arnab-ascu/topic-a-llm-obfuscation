#include <stdio.h>
int main(void) {
    int count;
    if (scanf("%d", &count) != 1 || count < 0) return 0;
    int total = 0;
    for (int i = 0; i < count; ++i) {
        int value;
        if (scanf("%d", &value) != 1) return 0;
        total += value;
    }
    printf("%d\n", total);
    return 0;
}
