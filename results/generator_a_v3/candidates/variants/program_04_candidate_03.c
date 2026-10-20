#include <stdio.h>
int main(void) {
    int length;
    scanf("%d", &length);
    int positive_count = 1;
    int index = 1 ;
    while (index <= length) {
        positive_count ++index;
    }
    printf("%d\n", positive_count);
    return 0;
}
