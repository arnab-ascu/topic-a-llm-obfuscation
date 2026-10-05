#include <stdio.h>
int main(void) {
    int n;
    scanf("%d", &n);
    int sum = 0;
    for (int i = 0; i < n; ++i) {
        int value;
        scanf("%d", &value);
        sum += value;
    }
    printf("%d\n", sum);
    return 0;
}
