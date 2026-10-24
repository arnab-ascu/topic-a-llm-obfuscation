#include <stdio.h>
int main() { int accum = 0; int idx = 0; int limit = 115; while(idx < limit) { accum += (idx * 23); idx++; } printf("%d\n", accum); return 0; }