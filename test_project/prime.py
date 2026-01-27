import math

__all__ = ["is_prime"]


def is_prime(n: int) -> bool:
    """
    Return True if n is a prime number, else False.

    Parameters
    ----------
    n : int
        The integer to test for primality.

    Returns
    -------
    bool
        True if n is prime, False otherwise.

    Raises
    ------
    TypeError
        If n is not an integer or is a bool.

    Examples
    --------
    >>> is_prime(2)
    True
    >>> is_prime(4)
    False
    >>> is_prime(17)
    True
    """
    if not isinstance(n, int) or isinstance(n, bool):
        raise TypeError("n must be an integer, not a bool or other type")

    if n < 2:
        return False
    if n in (2, 3):
        return True
    if n % 2 == 0:
        return False

    limit = math.isqrt(n)
    i = 5
    while i <= limit:
        if n % i == 0 or n % (i + 2) == 0:
            return False
        i += 6
    return True


if __name__ == "__main__":
    sample_numbers = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 13, 17, 19, 20, 23, 24, 29, 30]
    for num in sample_numbers:
        print(f"{num}: {is_prime(num)}")