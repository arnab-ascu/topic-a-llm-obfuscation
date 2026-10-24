#include <stdio.h>
int main() { int vec[4] = {20, 21, 22, 23}; int *ptr = vec; printf("%d\n", *(ptr + 0) + *(ptr + 3)); return 0; }