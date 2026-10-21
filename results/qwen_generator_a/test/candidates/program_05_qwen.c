#include <stdio.h>
int main(void) {
    int count;
    scanf("%d", &count);
    int total = 0;
    for (int i = 0; i < count; ++i) {
        int val;
        scanf("%d", &val);
        total += val;
    }
    printf("%d\n", total);
    return 0;
}
