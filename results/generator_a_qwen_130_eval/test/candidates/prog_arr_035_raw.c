#include <stdio.h>
int main() { int vec[4] = {35, 36, 37, 38}; int *ptr = vec; printf("%d\n", *(ptr + 0) + *(ptr + 3)); return 0; }
