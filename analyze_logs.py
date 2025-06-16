import json

# Funktion zum Einlesen der JSON-Logdatei
def read_json_log(file_path):
    with open(file_path, 'r') as file:
        return json.load(file)

# Beispielaufruf der Funktion
log_data = read_json_log('log.json')
print(log_data)