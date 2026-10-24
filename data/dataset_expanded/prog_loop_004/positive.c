#include <stdio.h>
int main() { int accum = 0; int idx = 0; int limit = 20; while(idx < limit) { accum += (idx * 4); idx++; } printf("%d\n", accum); return 0; }