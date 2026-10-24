#include <stdio.h>
int main() { int sum = 0; int n = 30; for(int idx=0; idx<n; idx++) sum += (idx * 6); printf("%d\n", sum); return 0; }