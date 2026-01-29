import os
import requests
import openai
from utils.openai_compat import prepare_openai_params
from dotenv import load_dotenv
import base64

# Load environment variables
load_dotenv()

def test_dataforseo():
    print("--- Testing DataForSEO API ---")
    user = os.getenv("DATAFORSEO_USER")
    password = os.getenv("DATAFORSEO_PASS")
    
    if not user or not password:
        print("Error: DATAFORSEO_USER or DATAFORSEO_PASS not found in .env")
        return

    # Endpoint from setup_instructions.md
    url = "https://api.dataforseo.com/v3/serp/google/organic/live/advanced"
    
    # Create auth header manually to be sure
    creds = f"{user}:{password}"
    token = base64.b64encode(creds.encode()).decode()
    headers = {
        "Authorization": f"Basic {token}",
        "Content-Type": "application/json"
    }
    
    payload = [{
        "keyword": "test",
        "location_code": 2276,
        "language_code": "de"
    }]
    
    try:
        response = requests.post(url, json=payload, headers=headers)
        print(f"Status Code: {response.status_code}")
        if response.status_code == 200:
            print("Success! Response snippet:")
            print(str(response.json())[:200])
        else:
            print("Failed!")
            print(response.text)
    except Exception as e:
        print(f"Exception: {e}")

def test_openai():
    print("\n--- Testing OpenAI API ---")
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("Error: OPENAI_API_KEY not found in .env")
        return

    client = openai.OpenAI(api_key=api_key)
    
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": "Hello, are you working?"}],
            max_tokens=10
        )
        print("Success! Response:")
        print(response.choices[0].message.content)
    except Exception as e:
        print(f"Exception: {e}")

if __name__ == "__main__":
    test_dataforseo()
    test_openai()
