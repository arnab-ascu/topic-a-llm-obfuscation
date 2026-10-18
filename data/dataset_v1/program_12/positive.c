#include <stdio.h>
int main() { int num = 5; int acc = 1; int iter = 1; while(iter <= num) { acc = acc * iter; iter++; } printf("%d\n", acc); return 0; }