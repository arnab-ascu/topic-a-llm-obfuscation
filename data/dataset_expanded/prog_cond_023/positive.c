#include <stdio.h>
int main() { int val = 69; int thresh = 46; int res = (val > thresh) ? 1 : 0; if (res == 1) { printf("ABOVE\n"); } else { printf("BELOW\n"); } return 0; }