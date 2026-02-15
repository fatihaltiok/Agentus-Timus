def multiply(a, b):
    """Gibt das Produkt von a und b zurück."""
    return a * b


def square(n: int | float) -> int | float:
    """
    Gibt die quadratische Potenz von n zurück.

    Parameter
    ----------
    n : int | float
        Die Zahl, die quadriert werden soll.

    Returns
    -------
    int | float
        Das Quadrat von n.

    Raises
    ------
    TypeError
        Wenn n kein int oder float ist.
    """
    if not isinstance(n, (int, float)):
        raise TypeError(
            f"Parameter n muss ein int oder float sein, "
            f"aber {type(n).__name__} wurde übergeben."
        )
    return n * n
