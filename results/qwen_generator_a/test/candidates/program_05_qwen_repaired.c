#include <stdio.h>
int main(void) {
    int count;
    scanf("%d", &count);
    int total = 0;
    {
        int i = 0;
        while (i < count) {
            int val;
            scanf("%d", &val);
            total = total + (val);

            ++i;
        }
    }
    printf("%d\n", total);
    return 0;
}
