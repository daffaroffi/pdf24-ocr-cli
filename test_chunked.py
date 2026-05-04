import requests
import os
import random

def multipart_generator(file_path, boundary):
    filename = os.path.basename(file_path)
    start = (
        f"--{boundary}\r\n"
        f"Content-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\n"
        f"Content-Type: application/pdf\r\n\r\n"
    ).encode('utf-8')
    yield start
    
    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(81920)
            if not chunk:
                break
            yield chunk
            
    end = f"\r\n--{boundary}--\r\n".encode('utf-8')
    yield end

boundary = '----PDF24UploadBoundary'
headers = {
    'Content-Type': f'multipart/form-data; boundary={boundary}',
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36',
    'Origin': 'https://tools.pdf24.org',
    'Referer': 'https://tools.pdf24.org/en/ocr-pdf'
}

server_num = random.randint(0, 29)
base_url = f"https://filetools{server_num}.pdf24.org/client.php"
print(f"[*] Testing chunked upload to {base_url}")

response = requests.post(f"{base_url}?action=upload", data=multipart_generator("sample.pdf", boundary), headers=headers)
print("Status:", response.status_code)
print("Response:", response.text)
