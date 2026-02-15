#!/usr/bin/env python3
"""
Simple Moondream API Test mit erhöhtem Timeout
"""
import requests
import base64
import sys
from pathlib import Path

def test_moondream_api():
    # Einfaches Bild nehmen
    image_path = "/home/fatih-ubuntu/dev/timus/google-cloud-shell.png"

    # Base64 encode das Bild
    with open(image_path, "rb") as f:
        image_base64 = base64.b64encode(f.read()).decode()

    # API Konfiguration
    api_base = "http://localhost:2022/v1"

    print(f"Testing Moondream API at {api_base}")
    print(f"Image: {image_path}")

    # Test 1: Caption API (einfachste)
    print("\n1. Testing /v1/caption with 'image' parameter (300s timeout)...")
    try:
        response = requests.post(
            f"{api_base}/caption",
            json={"image": image_base64},
            timeout=(60, 300)
        )
        print(f"Status: {response.status_code}")
        print(f"Response: {response.text}")
    except Exception as e:
        print(f"ERROR: {e}")

    print("\n2. Testing /v1/caption with 'image_url' parameter (data URL)...")
    try:
        # Try data URL format
        data_url = f"data:image/png;base64,{image_base64}"
        response = requests.post(
            f"{api_base}/caption",
            json={"image_url": data_url},
            timeout=(60, 300)
        )
        print(f"Status: {response.status_code}")
        print(f"Response: {response.text}")
    except Exception as e:
        print(f"ERROR: {e}")

    # Test 3: Query API mit data URL
    print("\n3. Testing /v1/query with 'image_url' (data URL format)...")
    try:
        data_url = f"data:image/png;base64,{image_base64}"
        response = requests.post(
            f"{api_base}/query",
            json={
                "image_url": data_url,
                "question": "What do you see in this image?"
            },
            timeout=(60, 300)
        )
        print(f"Status: {response.status_code}")
        print(f"Response: {response.text}")
    except Exception as e:
        print(f"ERROR: {e}")

    # Test 4: Point API mit data URL
    print("\n4. Testing /v1/point with 'image_url' (data URL format)...")
    try:
        data_url = f"data:image/png;base64,{image_base64}"
        response = requests.post(
            f"{api_base}/point",
            json={
                "image_url": data_url,
                "object": "button"
            },
            timeout=(60, 300)
        )
        print(f"Status: {response.status_code}")
        print(f"Response: {response.text}")
    except Exception as e:
        print(f"ERROR: {e}")

if __name__ == "__main__":
    test_moondream_api()
