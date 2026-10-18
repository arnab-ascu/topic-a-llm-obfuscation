#include <stdio.h>
int main(void) {
    int val;
    scanf("%d", &val);
    int mask = (val < 0) ? -1 : 0;
    int magnitude = (val ^ mask) - mask;
    printf("%d\n", magnitude);
    return 0;
}
