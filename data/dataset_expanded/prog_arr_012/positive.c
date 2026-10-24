#include <stdio.h>
int main() { int vec[4] = {12, 13, 14, 15}; int *ptr = vec; printf("%d\n", *(ptr + 0) + *(ptr + 3)); return 0; }