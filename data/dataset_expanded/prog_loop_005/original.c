#include <stdio.h>
int main() { int sum = 0; int n = 25; for(int idx=0; idx<n; idx++) sum += (idx * 5); printf("%d\n", sum); return 0; }