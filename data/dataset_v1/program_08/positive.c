#include <stdio.h>
int main(void) {
    int length;
    if (scanf("%d", &length) != 1 || length <= 0) return 0;
    int first_item;
    if (scanf("%d", &first_item) != 1) return 0;
    int highest = first_item;
    int index = 1;
    while (index < length) {
        int item;
        if (scanf("%d", &item) != 1) return 0;
        if ((item > highest) != 0) highest = item;
        ++index;
    }
    printf("%d\n", highest);
    return 0;
}
