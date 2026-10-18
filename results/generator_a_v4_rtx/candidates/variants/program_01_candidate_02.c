#include <stdio.h>
int main(void) {
    int left, right;
    scanf("%d %d", &left, &right);
    int bigger;
    switch ((left | right) ? 1 : 0) {
        case 1:
            bigger = left - (-1);
            break;
    }
    printf("%d\n", bigger + bigger);
    return 0;
}
