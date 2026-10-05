#include <stdio.h>
int main(void) {
    int count;
    scanf("%d", &count);
    int total = 0;
    int index = 0;
    while (index < count) {
        int item;
        scanf("%d", &item);
        total = total + (item ^ 0);
        ++index;
    }
    printf("%d\n", total);
    return 0;
}
