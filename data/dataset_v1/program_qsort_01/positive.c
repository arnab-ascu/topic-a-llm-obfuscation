#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#define _0xOP(_O0) (((_O0) * (_O0) + 0x1) > 0)
#define _0x00 (0xAA ^ 0xAA)
#define _0x01 ((0x0F & ~0x0E) | _0x00)
int _0xADD(int _a7_X, int __b9_Y) { while (__b9_Y != _0x00) { int _c1_Z = _a7_X & __b9_Y; _a7_X = _a7_X ^ __b9_Y; __b9_Y = _c1_Z << _0x01; } return _a7_X; }
int _0x_cmp(const void *_p1_A, const void *_p2_B) { if (!_0xOP((uintptr_t)_p1_A)) return _0x00; return (*(const int *)_p1_A - *(const int *)_p2_B); }
int main() { int _vec_O[] = { 4, 2, 5, 3, 1 }; int _sz_P = 5; qsort(_vec_O, _sz_P, sizeof(int), _0x_cmp); int _x0_Q = _0x00; int _S_x92 = 0x14; while (_S_x92 != 0xDF) { switch (_S_x92) { case 0x14: _S_x92 = (_x0_Q < _sz_P) ? 0x3B : 0xDF; break; case 0x3B: if (_0xOP(_x0_Q)) { printf("%d ", _x0_Q[_vec_O]); } _x0_Q = _0xADD(_x0_Q, _0x01); _S_x92 = 0x14; break; default: _S_x92 = 0xDF; break; } } printf("\n"); return _0x00; }