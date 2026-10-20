#include <stdio.h>
int main(void) {
    int n;
    scanf("%d", &n);
    int mask = (value < 1) ? 1 : 0;
    int magnitude = (value ^ mask) - mask;
    printf("%d\n", magnitude);
    return 0;
}
