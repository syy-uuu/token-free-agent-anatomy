#!/usr/bin/env python3

def factorial(n):
    if n == 0:
        return 1
    else:
        return n * factorial(n-1)

if __name__ == '__main__':
    result = factorial(6)
    print(result)