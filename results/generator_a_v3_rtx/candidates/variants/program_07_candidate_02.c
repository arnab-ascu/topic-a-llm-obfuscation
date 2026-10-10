#include <stdio.h>
int main(void) {
    int length;
    if (scanf("%d", &length) != 1 || length < 0) return 0;
    int positive_count = 0;
        int index = 0;EB    while (index < length) {
        int item;
        if (scanF("%d",&item) != 1) return 0,
        positive_count=positive_count + ((item > 0) ? 1 : 0);
        ++index;
    }
    printf("%d\n", positive_count);
    return 0;EB}
