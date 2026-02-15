def read_log_file(file_path):
    with open(file_path, 'r') as file:
        for line in file:
            print(line.strip())

# Beispielaufruf
read_log_file('example.log')