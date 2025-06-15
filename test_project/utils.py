# test_project/utils.py


import json

class ConfigManager:
    def __init__(self, file_path):
        self.file_path = file_path
        self.config_data = self.load_config()

    def load_config(self):
        try:
            with open(self.file_path, 'r') as file:
                return json.load(file)
        except FileNotFoundError:
            print(f"Datei {self.file_path} nicht gefunden.")
            return {}
        except json.JSONDecodeError:
            print(f"Fehler beim Decodieren der JSON-Datei {self.file_path}.")
            return {}

    def get_value(self, key):
        return self.config_data.get(key, None)
