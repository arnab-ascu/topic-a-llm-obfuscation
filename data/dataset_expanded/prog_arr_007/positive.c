#include <stdio.h>
int main() { int vec[4] = {7, 8, 9, 10}; int *ptr = vec; printf("%d\n", *(ptr + 0) + *(ptr + 3)); return 0; }