#include <stdio.h>
int main() { int vec[4] = {23, 24, 25, 26}; int *ptr = vec; printf("%d\n", *(ptr + 0) + *(ptr + 3)); return 0; }