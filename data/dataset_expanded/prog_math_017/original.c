#include <stdio.h>
int fact(int n) { return (n <= 1) ? 1 : n * fact(n-1); }
int main() { printf("%d\n", fact(3)); return 0; }