# test_project/utils.py

# This file will contain utility classes and functions.
import os
import json

def get_project_root():
    """Returns the root directory of the project."""
    # A simple helper function that might already exist.
    return os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

class ConfigManager:
    """Eine Klasse zum Verwalten von Konfigurationen aus einer JSON-Datei."""

    def __init__(self, file_path):
        self.file_path = file_path
        self.config_data = None

    def load_config(self):
        """Lädt die Konfiguration aus einer JSON-Datei."""
        with open(self.file_path, 'r') as file:
            self.config_data = json.load(file)

    def get_value(self, key):
        """Gibt den Wert für einen gegebenen Schlüssel zurück."""
        if self.config_data is None:
            raise ValueError("Konfiguration nicht geladen. Bitte zuerst load_config() aufrufen.")
        return self.config_data.get(key)
