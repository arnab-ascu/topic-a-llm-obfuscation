#include <stdio.h>
int main() { int vec[4] = {8, 9, 10, 11}; int *ptr = vec; printf("%d\n", *(ptr + 0) + *(ptr + 3)); return 0; }