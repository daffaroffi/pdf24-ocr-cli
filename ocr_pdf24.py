import requests
import random
import time
import os
import sys
import json
import threading
import itertools

class Spinner:
    def __init__(self, message="[*] Processing..."):
        self.spinner = itertools.cycle(['-', '/', '|', '\\'])
        self.busy = False
        self.delay = 0.1
        self.message = message
        self.thread = None

    def spinner_task(self):
        while self.busy:
            print(f"\r{self.message} {next(self.spinner)}", end="", flush=True)
            time.sleep(self.delay)

    def __enter__(self):
        self.busy = True
        self.thread = threading.Thread(target=self.spinner_task)
        self.thread.start()

    def __exit__(self, exception_type, exception_value, traceback):
        self.busy = False
        time.sleep(self.delay)
        print("\r" + " " * (len(self.message) + 5) + "\r", end="", flush=True)

import http.client
import urllib.parse
import ssl

def stream_upload(base_url, file_path):
    url_parts = urllib.parse.urlparse(base_url)
    host = url_parts.netloc
    path = url_parts.path + "?action=upload"
    
    boundary = "----WebKitFormBoundaryPDF24Upload"
    filename = os.path.basename(file_path)
    
    head = (
        f"--{boundary}\r\n"
        f"Content-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\n"
        f"Content-Type: application/pdf\r\n\r\n"
    ).encode('utf-8')
    
    tail = f"\r\n--{boundary}--\r\n".encode('utf-8')
    
    file_size = os.path.getsize(file_path)
    total_len = len(head) + file_size + len(tail)
    
    headers = {
        'Content-Type': f'multipart/form-data; boundary={boundary}',
        'Content-Length': str(total_len),
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Origin': 'https://tools.pdf24.org',
        'Referer': 'https://tools.pdf24.org/en/ocr-pdf',
        'Connection': 'keep-alive'
    }
    
    context = ssl.create_default_context()
    # High timeout for slow connections (e.g., 5 minutes)
    conn = http.client.HTTPSConnection(host, context=context, timeout=300) 
    
    conn.putrequest("POST", path)
    for k, v in headers.items():
        conn.putheader(k, v)
    conn.endheaders()
    
    conn.send(head)
    
    seen = 0
    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(65536) # Read in 64KB chunks
            if not chunk:
                break
            conn.send(chunk)
            seen += len(chunk)
            percent = (seen / file_size) * 100
            bar = '#' * int(percent / 5)
            spaces = ' ' * (20 - len(bar))
            print(f"\r[*] Uploading: [{bar}{spaces}] {percent:3.1f}%", end="", flush=True)
            
    conn.send(tail)
    print() # Newline after progress bar
    
    resp = conn.getresponse()
    body = resp.read()
    conn.close()
    
    if resp.status == 200:
        return json.loads(body.decode('utf-8'))[0]
    else:
        raise Exception(f"HTTP {resp.status}: {body.decode('utf-8')}")

def ocr_pdf24(input_file, lang='en', output_file=None):
    if not os.path.exists(input_file):
        print(f"\033[91m[!] Error: File {input_file} not found.\033[0m")
        return

    max_retries = 3
    retry_count = 0
    upload_result = None
    base_url = ""
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Origin': 'https://tools.pdf24.org',
        'Referer': 'https://tools.pdf24.org/en/ocr-pdf'
    })

    # --- PHASE 1: UPLOAD (with Server Fallback) ---
    while retry_count < max_retries:
        server_num = random.randint(0, 29)
        base_url = f"https://filetools{server_num}.pdf24.org/client.php"
        
        if retry_count > 0:
            print(f"\033[93m[*] Retrying with different server (Attempt {retry_count+1}/{max_retries})...\033[0m")
        
        print(f"\033[94m[*] Using server: {base_url}\033[0m")

        try:
            upload_result = stream_upload(base_url, input_file)
            break
        except Exception as e:
            print(f"\n\033[93m[!] Server error: {e}. Switching server...\033[0m")
        
        retry_count += 1
        time.sleep(2)

    if not upload_result:
        print(f"\033[91m[!] Failed to upload file after {max_retries} attempts.\033[0m")
        return
        
    print(f"\033[92m[+] Uploaded. Server File ID: {upload_result['file']}\033[0m")

    # --- PHASE 2: START OCR JOB ---
    # Map common 2-letter codes to Tesseract 3-letter codes
    lang_map = {
        'id': 'ind',
        'en': 'eng',
        'ar': 'ara'
    }
    tesseract_lang = lang_map.get(lang.lower(), lang)
    
    print(f"[*] Starting OCR job (lang={tesseract_lang}, force=True)...")
    payload = {
        "files": [upload_result],
        "langCode": tesseract_lang,
        "outputType": "pdf",
        "removeBackground": False,
        "rotatePages": False,
        "deskew": False,
        "clean": False,
        "forceOcr": True, # CRITICAL: Forces OCR even if text is detected
        "joinFiles": False
    }
    
    try:
        response = session.post(f"{base_url}?action=ocrPdf", json=payload, timeout=(10, 40))
        if response.status_code != 200:
            print(f"\033[91m[-] Job creation failed: {response.status_code}\033[0m")
            return
        job_id = response.json()['jobId']
    except Exception as e:
        print(f"\033[91m[!] Error starting job: {e}\033[0m")
        return

    print(f"\033[92m[+] Job started. Job ID: {job_id}\033[0m")

    # --- PHASE 3: POLL STATUS ---
    with Spinner("[*] Processing OCR..."):
        while True:
            try:
                status_payload = {"jobId": job_id}
                response = session.post(f"{base_url}?action=getStatus", json=status_payload, timeout=20)
                
                if response.status_code != 200:
                    time.sleep(5) # Wait before retry
                    continue
                    
                result = response.json()
                if result.get('status') == 'done':
                    break
                elif result.get('status') == 'error':
                    print(f"\n\033[91m[-] OCR failed: {result.get('error', 'Unknown error')}\033[0m")
                    return
                
                time.sleep(2)
            except requests.exceptions.Timeout:
                continue 
            except Exception:
                break
    
    print(f"\033[92m[+] OCR finished!\033[0m")

    # --- PHASE 4: DOWNLOAD ---
    if output_file is None:
        output_file = "ocr_result_" + os.path.basename(input_file)
        
    print(f"[*] Downloading result to {output_file}...")
    download_url = f"{base_url}?action=downloadJobResult&jobId={job_id}"
    try:
        response = session.get(download_url, timeout=(10, 300)) # Long timeout for download
        if response.status_code == 200:
            with open(output_file, 'wb') as f:
                f.write(response.content)
            print(f"\033[92m[+] Success! File saved as {output_file}\033[0m")
        else:
            print(f"\033[91m[-] Download failed: {response.status_code}\033[0m")
    except Exception as e:
        print(f"\033[91m[!] Download error: {e}\033[0m")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("\033[93mUsage: python3 ocr_pdf24.py <input_pdf> [lang]\033[0m")
    else:
        file_path = sys.argv[1]
        language = sys.argv[2] if len(sys.argv) > 2 else 'en'
        ocr_pdf24(file_path, language)
