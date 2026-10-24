#include <stdio.h>
int main() { int sum = 0; int n = 60; for(int idx=0; idx<n; idx++) sum += (idx * 12); printf("%d\n", sum); return 0; }