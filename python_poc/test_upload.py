import requests
import random
import os

session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36',
    'Origin': 'https://tools.pdf24.org',
    'Referer': 'https://tools.pdf24.org/en/ocr-pdf'
})

server_num = random.randint(0, 29)
base_url = f"https://filetools{server_num}.pdf24.org/client.php"
print(f"[*] Testing plain upload to {base_url}")

with open("sample.pdf", "rb") as f:
    files = {'file': ('sample.pdf', f, 'application/pdf')}
    response = session.post(f"{base_url}?action=upload", files=files, timeout=60)
    print("Status:", response.status_code)
    print("Response:", response.text)
