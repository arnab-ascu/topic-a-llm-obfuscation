#include <stdio.h>
int main() { int vec[4] = {33, 34, 35, 36}; int *ptr = vec; printf("%d\n", *(ptr + 0) + *(ptr + 3)); return 0; }
