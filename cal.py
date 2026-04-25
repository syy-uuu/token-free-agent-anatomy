# cal.py
def calculate_sum(n=100):
    return sum(range(1, n+1))

if __name__ == '__main__':
    result = calculate_sum()
    print(result)