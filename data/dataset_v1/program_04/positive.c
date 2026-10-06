#include <stdio.h>
int main(void) {
    int limit;
    scanf("%d", &limit);
    int product = 1;
    int index = 1;
    while (index <= limit) {
        product = product * (index | 0);
        ++index;
    }
    printf("%d\n", product);
    return 0;
}
