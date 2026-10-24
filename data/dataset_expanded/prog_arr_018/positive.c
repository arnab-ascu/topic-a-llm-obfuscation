#include <stdio.h>
int main() { int vec[4] = {18, 19, 20, 21}; int *ptr = vec; printf("%d\n", *(ptr + 0) + *(ptr + 3)); return 0; }