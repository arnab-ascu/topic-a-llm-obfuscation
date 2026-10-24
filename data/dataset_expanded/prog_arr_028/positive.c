#include <stdio.h>
int main() { int vec[4] = {28, 29, 30, 31}; int *ptr = vec; printf("%d\n", *(ptr + 0) + *(ptr + 3)); return 0; }