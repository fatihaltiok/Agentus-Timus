import json
import numpy as np

# Funktion zum Einlesen der JSON-Logdatei
def read_json_log(file_path):
    with open(file_path, 'r') as file:
        return json.load(file)

# Funktion zur Erkennung von Anomalien in den Logdaten
def detect_anomalies(log_data, threshold=3):
    anomalies = []
    for entry in log_data:
        for key, value in entry.items():
            if isinstance(value, (int, float)):
                mean = np.mean([e[key] for e in log_data if isinstance(e[key], (int, float))])
                std_dev = np.std([e[key] for e in log_data if isinstance(e[key], (int, float))])
                if std_dev > 0 and (value > mean + threshold * std_dev or value < mean - threshold * std_dev):
                    anomalies.append((entry, key, value))
    return anomalies
log_data = read_json_log('log.json')
print(log_data)

# Anomalien in den Logdaten erkennen
anomalies = detect_anomalies(log_data)
print("Anomalies detected:", anomalies)
