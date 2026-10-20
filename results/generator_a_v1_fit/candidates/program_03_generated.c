int value;
    scanf("%d", &value);
    int magnitude;
    scanf("%d", &value);
    if (magnitude < 0) {
        magnitude = -magnitude;
    }
    printf("%d\n", magnitude);
    return 0;
}
