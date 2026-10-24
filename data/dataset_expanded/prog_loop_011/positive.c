#include <stdio.h>
int main() { int accum = 0; int idx = 0; int limit = 55; while(idx < limit) { accum += (idx * 11); idx++; } printf("%d\n", accum); return 0; }