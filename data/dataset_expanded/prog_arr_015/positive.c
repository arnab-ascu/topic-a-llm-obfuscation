#include <stdio.h>
int main() { int vec[4] = {15, 16, 17, 18}; int *ptr = vec; printf("%d\n", *(ptr + 0) + *(ptr + 3)); return 0; }