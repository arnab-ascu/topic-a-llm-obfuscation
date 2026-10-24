#include <stdio.h>
int main() { int sum = 0; int n = 10; for(int idx=0; idx<n; idx++) sum += (idx * 2); printf("%d\n", sum); return 0; }