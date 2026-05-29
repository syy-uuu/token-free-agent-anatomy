import calculator

def test_multiply_integers():
    assert calculator.multiply(2, 3) == 6
def test_multiply_negative_numbers():
    assert calculator.multiply(-1, -1) == 1
def test_multiply_positive_and_negative_number():
    assert calculator.multiply(4, -2) == -8
