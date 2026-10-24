#include <stdio.h>
int main() { int vec[4] = {21, 22, 23, 24}; int *ptr = vec; printf("%d\n", *(ptr + 0) + *(ptr + 3)); return 0; }