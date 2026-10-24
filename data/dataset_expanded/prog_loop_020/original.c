#include <stdio.h>
int main() { int sum = 0; int n = 100; for(int idx=0; idx<n; idx++) sum += (idx * 20); printf("%d\n", sum); return 0; }