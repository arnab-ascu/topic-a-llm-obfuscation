#include <stdio.h>
int main() { int vec[4] = {27, 28, 29, 30}; int *ptr = vec; printf("%d\n", *(ptr + 0) + *(ptr + 3)); return 0; }