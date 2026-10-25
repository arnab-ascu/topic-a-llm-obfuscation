#include <stdio.h>
int compute_fact(int num) { int res = 1; int curr = 1; while(curr <= num) { res *= curr; curr++; } return res; }
int main() { printf("%d\n", compute_fact(3)); return 0; }
