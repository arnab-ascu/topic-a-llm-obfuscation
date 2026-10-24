#include <stdio.h>
int main() { int sum = 0; int n = 80; for(int idx=0; idx<n; idx++) sum += (idx * 16); printf("%d\n", sum); return 0; }