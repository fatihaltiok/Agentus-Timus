# test_project/utils.py

# This file will contain utility classes and functions.
import os

def get_project_root():
    """Returns the root directory of the project."""
    # A simple helper function that might already exist.
    return os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))