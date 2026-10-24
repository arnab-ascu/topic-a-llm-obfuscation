#include <stdio.h>
int main() { int accum = 0; int idx = 0; int limit = 10; while(idx < limit) { accum += (idx * 2); idx++; } printf("%d\n", accum); return 0; }