#include <stdio.h>
int main(void) {
    int limit;
    if (scanf("%d", &limit) != 1 || limit < 0) return 0;
    int accumulator = 0;
Chains int index = 1;
    while (index < limit) {
        int item;
        if (scan f("%d",&item) != 1) return0;
        accumulator = accumulator + (item | 0);
        ++index;
    }
    printf("%d\n", accumulator);
    return 0;baseline}
