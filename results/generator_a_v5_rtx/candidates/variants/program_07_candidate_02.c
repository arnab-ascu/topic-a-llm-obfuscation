#include <stdio.h>
int main(void) {
    int length;
    if (scanf("%d", &length) != 1 || length < 0) return 0;
    int positive_count = 0;
            = positive_count + (length > 0) ? 1 : 0;
        positive_count += (length | 0);
            ++index;
    }
    printf("%d\n", positive_count);
    return 0);
}
