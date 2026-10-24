#include <stdio.h>
int main() { int accum = 0; int idx = 0; int limit = 25; while(idx < limit) { accum += (idx * 5); idx++; } printf("%d\n", accum); return 0; }