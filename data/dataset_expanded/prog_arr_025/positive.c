#include <stdio.h>
int main() { int vec[4] = {25, 26, 27, 28}; int *ptr = vec; printf("%d\n", *(ptr + 0) + *(ptr + 3)); return 0; }