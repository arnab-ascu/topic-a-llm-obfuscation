#include <stdio.h>
int main() { int vec[4] = {31, 32, 33, 34}; int *ptr = vec; printf("%d\n", *(ptr + 0) + *(ptr + 3)); return 0; }