# test_project/user.py
"""
User model module.

Provides a `User` class with strict type validation, email format checking,
and safe handling of mutable attributes. Designed for Python 3.10+ and fully
PEP8 compliant with type hints.

No external dependencies are required.
"""

from __future__ import annotations

import copy
import re
from typing import Any, Dict, Optional

# Compiled regex pattern for validating email addresses.
# Allows alphanumeric characters, dot, underscore, hyphen, plus in the local part,
# domain with optional subdomains, and TLDs of 2-63 alphabetic characters.
EMAIL_REGEX = re.compile(
    r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,63}$"
)


class User:
    """
    Represents a user with contact and status information.

    Attributes
    ----------
    email : str
        User's email address (validated).
    first_name : Optional[str]
        User's first name.
    last_name : Optional[str]
        User's last name.
    is_active : bool
        Flag indicating whether the user is active.
    metadata : Optional[dict[str, Any]]
        Additional arbitrary data associated with the user.
    """

    def __init__(
        self,
        email: str,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        is_active: bool = True,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Initialize a new User instance with validation and safe copying.

        Parameters
        ----------
        email : str
            The user's email address. Must match the compiled EMAIL_REGEX.
        first_name : Optional[str]
            The user's first name.
        last_name : Optional[str]
            The user's last name.
        is_active : bool
            Whether the user is currently active.
        metadata : Optional[dict[str, Any]]
            Additional data to store with the user.

        Raises
        ------
        TypeError
            If any argument is of an unexpected type.
        ValueError
            If the email format is invalid.
        """
        # Type validation
        if not isinstance(email, str):
            raise TypeError(f"email must be a str, got {type(email).__name__}")
        if first_name is not None and not isinstance(first_name, str):
            raise TypeError(f"first_name must be a str or None, got {type(first_name).__name__}")
        if last_name is not None and not isinstance(last_name, str):
            raise TypeError(f"last_name must be a str or None, got {type(last_name).__name__}")
        if not isinstance(is_active, bool):
            raise TypeError(f"is_active must be a bool, got {type(is_active).__name__}")
        if metadata is not None and not isinstance(metadata, dict):
            raise TypeError(f"metadata must be a dict or None, got {type(metadata).__name__}")

        # Email format validation
        if not EMAIL_REGEX.match(email):
            raise ValueError(f"Invalid email format: '{email}'")

        # Safe storage
        self.email: str = email
        self.first_name: Optional[str] = first_name
        self.last_name: Optional[str] = last_name
        self.is_active: bool = is_active
        self.metadata: Optional[Dict[str, Any]] = copy.deepcopy(metadata) if metadata is not None else None

    def validate_email(self) -> bool:
        """
        Check whether the stored email address matches the validation pattern.

        Returns
        -------
        bool
            True if the email is valid, False otherwise.
        """
        return bool(EMAIL_REGEX.match(self.email))

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert the User instance into a JSON-serializable dictionary.

        Returns
        -------
        dict[str, Any]
            Dictionary containing all user attributes. The metadata dictionary
            is deep‑copied to prevent external mutation.
        """
        return {
            "email": self.email,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "is_active": self.is_active,
            "metadata": copy.deepcopy(self.metadata) if self.metadata is not None else None,
        }