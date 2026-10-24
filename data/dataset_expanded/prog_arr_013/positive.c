#include <stdio.h>
int main() { int vec[4] = {13, 14, 15, 16}; int *ptr = vec; printf("%d\n", *(ptr + 0) + *(ptr + 3)); return 0; }