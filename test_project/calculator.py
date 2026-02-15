# test_project/calculator.py

"""
Utility module providing a `Calculator` class for basic arithmetic operations.

The class offers methods to add, subtract, multiply, and divide two numbers.
All methods perform type validation and raise appropriate exceptions for
invalid inputs or division by zero.

Example usage:

>>> calc = Calculator()
>>> calc.add(2, 3)
5.0
>>> calc.subtract(10, 4)
6.0
>>> calc.multiply(3, 5)
15.0
>>> calc.divide(20, 4)
5.0
"""

from numbers import Real
from typing import Union

Number = Union[int, float]

__all__ = ["Calculator"]


class Calculator:
    """
    A simple calculator for performing basic arithmetic operations.

    Methods
    -------
    add(a, b) -> float
        Return the sum of a and b.
    subtract(a, b) -> float
        Return the difference a - b.
    multiply(a, b) -> float
        Return the product a * b.
    divide(a, b) -> float
        Return the quotient a / b. Raises ValueError if b is zero.
    """

    @staticmethod
    def _validate_numbers(a: Number, b: Number) -> None:
        """
        Validate that both a and b are real numbers.

        Parameters
        ----------
        a : Number
            First operand.
        b : Number
            Second operand.

        Raises
        ------
        TypeError
            If either a or b is not an instance of Real.
        """
        if not isinstance(a, Real):
            raise TypeError(f"First argument must be a real number, got {type(a).__name__}")
        if not isinstance(b, Real):
            raise TypeError(f"Second argument must be a real number, got {type(b).__name__}")

    @staticmethod
    def add(a: Number, b: Number) -> float:
        """
        Return the sum of a and b.

        Parameters
        ----------
        a : Number
            First operand.
        b : Number
            Second operand.

        Returns
        -------
        float
            The sum of a and b.

        Raises
        ------
        TypeError
            If either a or b is not a real number.
        """
        Calculator._validate_numbers(a, b)
        return float(a + b)

    @staticmethod
    def subtract(a: Number, b: Number) -> float:
        """
        Return the difference a - b.

        Parameters
        ----------
        a : Number
            First operand.
        b : Number
            Second operand.

        Returns
        -------
        float
            The difference a - b.

        Raises
        ------
        TypeError
            If either a or b is not a real number.
        """
        Calculator._validate_numbers(a, b)
        return float(a - b)

    @staticmethod
    def multiply(a: Number, b: Number) -> float:
        """
        Return the product a * b.

        Parameters
        ----------
        a : Number
            First operand.
        b : Number
            Second operand.

        Returns
        -------
        float
            The product a * b.

        Raises
        ------
        TypeError
            If either a or b is not a real number.
        """
        Calculator._validate_numbers(a, b)
        return float(a * b)

    @staticmethod
    def divide(a: Number, b: Number) -> float:
        """
        Return the quotient a / b.

        Parameters
        ----------
        a : Number
            Numerator.
        b : Number
            Denominator.

        Returns
        -------
        float
            The quotient a / b.

        Raises
        ------
        TypeError
            If either a or b is not a real number.
        ValueError
            If b is zero.
        """
        Calculator._validate_numbers(a, b)
        if b == 0:
            raise ValueError("Division by zero is undefined.")
        return float(a / b)