import os
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials

SCOPES = ['https://www.googleapis.com/auth/calendar.readonly',
           'https://www.googleapis.com/auth/calendar.events']

# Pfad zur Client‑Secret‑Datei (credentials.json) muss im selben Verzeichnis liegen
client_secrets_file = os.path.join(os.path.dirname(__file__), 'credentials.json')

flow = InstalledAppFlow.from_client_secrets_file(client_secrets_file, SCOPES)
creds = flow.run_local_server(port=0)

token_path = os.path.join(os.path.dirname(__file__), 'token.json')
with open(token_path, 'w') as token_file:
    token_file.write(creds.to_json())
print(f'Credentials saved to {token_path}')
