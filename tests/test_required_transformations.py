from src.models.required_transformations import apply_required_transformations
SAMPLE = r"""#include <stdio.h>
int main(void) {
    int count;
    scanf("%d", &count);
    int total = 0;
    for (int i = 0; i < count; ++i) {
        int val;
        scanf("%d", &val);
        total += val;
    }
    printf("%d\\n", total);
    return 0;
}
"""
def main():
    transformed, steps = apply_required_transformations(SAMPLE)
    assert "for (" not in transformed, transformed
    assert "while (i < count)" in transformed, transformed
    assert "total = total + (val);" in transformed, transformed
    assert "rewrote canonical for-loop to while-loop" in steps, steps
    assert "expanded simple compound assignment +=" in steps, steps
    print("PASS: canonical for-loop and compound assignment repaired")
    print("Repair steps:", steps)
if __name__ == "__main__": main()
