#include <stdio.h>
int main() { int vec[4] = {1, 2, 3, 4}; int *ptr = vec; printf("%d\n", *(ptr + 0) + *(ptr + 3)); return 0; }