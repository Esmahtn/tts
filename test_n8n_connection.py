import requests
import json

url = "http://178.104.62.105:5678/webhook/shopping-assistant"
payload = {
    "userInput": "başlayalım",
    "sessionId": "test_antigravity_001"
}

print(f"Testing URL: {url}")
print(f"Payload: {json.dumps(payload)}")

try:
    response = requests.post(url, json=payload, timeout=10)
    print(f"Status Code: {response.status_code}")
    print("Response Content:")
    print(json.dumps(response.json(), indent=2, ensure_ascii=False))
except Exception as e:
    print(f"Error: {e}")
