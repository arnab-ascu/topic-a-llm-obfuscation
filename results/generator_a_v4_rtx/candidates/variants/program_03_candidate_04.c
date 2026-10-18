#include <stdio.h>
int main(void) {
    int value;
    scanf("%d", &value);
    int magnitude;
    if (value < 0) {
        value = -value;
    }
    printf("%d\n", magnitude);
    return 0;
}
