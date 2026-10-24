#include <stdio.h>
int main() { int val = 45; int thresh = 30; int res = (val > thresh) ? 1 : 0; if (res == 1) { printf("ABOVE\n"); } else { printf("BELOW\n"); } return 0; }