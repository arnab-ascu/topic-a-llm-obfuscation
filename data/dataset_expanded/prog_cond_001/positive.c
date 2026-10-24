#include <stdio.h>
int main() { int val = 3; int thresh = 2; int res = (val > thresh) ? 1 : 0; if (res == 1) { printf("ABOVE\n"); } else { printf("BELOW\n"); } return 0; }