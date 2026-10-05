#include <stdio.h>
int main(void) {
    int lhs, rhs;
    scanf("%d %d", &lhs, &rhs);
    int total;
    if ((lhs | rhs) == (lhs | rhs)) {
        total = lhs - (-rhs);
    } else {
        total = lhs - (-rhs);
    }
    printf("%d\n", total);
    return 0;
}
