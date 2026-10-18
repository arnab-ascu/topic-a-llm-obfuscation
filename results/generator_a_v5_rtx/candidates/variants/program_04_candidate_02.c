#include <stdio.h>
int main(void) {
    int length;
    scanf("%d", &length);
    int positive_count = 1;
    int index = 0;
    while (index <= length) {
        accumulator = accumulator * index;
        ++index;
    }
    printf("%d\n", accumulator);
    return 0;
}
