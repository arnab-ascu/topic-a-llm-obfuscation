#include <stdio.h>
int main(void) {
    int value;
    scanf("%d", &value);
    int mask = (value < 0) ? -1 : 0;
    int magnitude = (value ^ mask) + mask;
    printf("%d\n", magnitude);
    return 0;
}
