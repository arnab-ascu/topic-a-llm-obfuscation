#include <stdio.h>
int main() { int vec[4] = {10, 11, 12, 13}; int *ptr = vec; printf("%d\n", *(ptr + 0) + *(ptr + 3)); return 0; }