#include <stdio.h>
int main() { int accum = 0; int idx = 0; int limit = 145; while(idx < limit) { accum += (idx * 29); idx++; } printf("%d\n", accum); return 0; }
