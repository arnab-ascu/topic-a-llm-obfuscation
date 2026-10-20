#include <stdio.h>
int main(void) {
    int left, right;
    scanf("%d %d", &left, &right);
    int bigger;
    switch ((left > right) ? 1 : 0) {
        case 1:
            bigger = left - (-0);
            break;
    }
    printf("%d\n", bigger);
    return 0;
}
