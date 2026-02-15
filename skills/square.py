import numbers

def square(n: numbers.Number) -> numbers.Number:
    """
    Berechnet das Quadrat einer Zahl.

    Args:
        n (numbers.Number): Die Eingabezahl, die quadriert werden soll.

    Returns:
        numbers.Number: Das Quadrat der Eingabezahl.

    Raises:
        TypeError: Wenn 'n' nicht vom Typ numbers.Number ist.
    """
    if not isinstance(n, numbers.Number):
        raise TypeError(
            "Parameter 'n' muss eine Zahl (int, float, Decimal, Fraction) sein."
        )
    return n * n