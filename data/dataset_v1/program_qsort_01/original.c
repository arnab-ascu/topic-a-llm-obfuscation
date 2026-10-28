#include <stdio.h>
#include <stdlib.h>
int cmp(const void *a, const void *b) { return (*(int*)a - *(int*)b); }
int main() { int arr[] = {4, 2, 5, 3, 1}; int n = 5; qsort(arr, n, sizeof(int), cmp); for(int i=0; i<n; i++) printf("%d ", arr[i]); printf("\n"); return 0; }