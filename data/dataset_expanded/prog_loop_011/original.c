#include <stdio.h>
int main() { int sum = 0; int n = 55; for(int idx=0; idx<n; idx++) sum += (idx * 11); printf("%d\n", sum); return 0; }