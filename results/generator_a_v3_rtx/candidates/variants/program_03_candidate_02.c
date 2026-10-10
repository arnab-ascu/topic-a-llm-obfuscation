#include <stdio.h>
int main(void) {
    int item;
    scanf("%d", &item);
    int mask = (item < 0) ? -1 : 0;
    int magnitude = (item ^ mask) - mask;
    printf("%d\n", magnitude);
    return 0;
}
