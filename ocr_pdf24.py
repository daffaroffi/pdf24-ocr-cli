import requests
import random
import time
import os
import sys
import json
import threading
import itertools

class ProgressFile(object):
    def __init__(self, filename, mode):
        self.filename = filename
        self.fp = open(filename, mode)
        self.total_size = os.path.getsize(filename)
        self.seen_so_far = 0

    def read(self, size=-1):
        data = self.fp.read(size)
        self.seen_so_far += len(data)
        if self.total_size > 0:
            percent = (self.seen_so_far / self.total_size) * 100
            bar = '#' * int(percent / 5)
            spaces = ' ' * (20 - len(bar))
            print(f"\r[*] Uploading: [{bar}{spaces}] {percent:3.1f}%", end="", flush=True)
        return data

    def __len__(self):
        return self.total_size

    def close(self):
        self.fp.close()

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

def ocr_pdf24(input_file, lang='en', output_file=None):
    if not os.path.exists(input_file):
        print(f"\033[91m[!] Error: File {input_file} not found.\033[0m")
        return

    # 1. Select a random worker server
    server_num = random.randint(0, 29)
    base_url = f"https://filetools{server_num}.pdf24.org/client.php"
    print(f"\033[94m[*] Using server: {base_url}\033[0m")

    session = requests.Session()
    
    # 2. Upload the file with progress
    pf = ProgressFile(input_file, 'rb')
    try:
        files = {
            'file': (os.path.basename(input_file), pf, 'application/pdf')
        }
        # Timeout added to avoid hanging
        response = session.post(f"{base_url}?action=upload", files=files, timeout=60)
        print() # New line after progress bar
    except requests.exceptions.Timeout:
        print(f"\n\033[91m[!] Upload timed out. The server {base_url} might be slow.\033[0m")
        return
    except Exception as e:
        print(f"\n\033[91m[!] Upload error: {e}\033[0m")
        return
    finally:
        pf.close()
    
    if response.status_code != 200:
        print(f"\033[91m[-] Upload failed: {response.status_code}\033[0m")
        return
    
    try:
        upload_result = response.json()[0]
    except Exception:
        print(f"\033[91m[-] Invalid upload response: {response.text}\033[0m")
        return
        
    print(f"\033[92m[+] Uploaded. Server File ID: {upload_result['file']}\033[0m")

    # 3. Start OCR Job
    print(f"[*] Starting OCR job (lang={lang})...")
    payload = {
        "files": [upload_result],
        "langCode": lang,
        "outputType": "pdf",
        "removeBackground": False,
        "rotatePages": False,
        "deskew": False,
        "clean": False,
        "forceOcr": False,
        "joinFiles": False
    }
    
    try:
        response = session.post(f"{base_url}?action=ocrPdf", json=payload, timeout=30)
    except requests.exceptions.Timeout:
        print(f"\033[91m[!] OCR start timed out.\033[0m")
        return
        
    if response.status_code != 200:
        print(f"\033[91m[-] Job creation failed: {response.status_code}\033[0m")
        return
    
    job_id = response.json()['jobId']
    print(f"\033[92m[+] Job started. Job ID: {job_id}\033[0m")

    # 4. Poll Status with Spinner
    with Spinner("[*] Processing OCR..."):
        while True:
            try:
                status_payload = {"jobId": job_id}
                response = session.post(f"{base_url}?action=getStatus", json=status_payload, timeout=20)
                
                if response.status_code != 200:
                    print(f"\n\033[91m[-] Status check failed: {response.status_code}\033[0m")
                    break
                    
                result = response.json()
                if result.get('status') == 'done':
                    break
                elif result.get('status') == 'error':
                    print(f"\n\033[91m[-] OCR failed: {result.get('error', 'Unknown error')}\033[0m")
                    return
                
                time.sleep(2)
            except requests.exceptions.Timeout:
                continue # Keep trying on status timeout
            except Exception:
                break
    
    print(f"\033[92m[+] OCR finished!\033[0m")

    # 5. Download Result
    if output_file is None:
        output_file = "ocr_result_" + os.path.basename(input_file)
        
    print(f"[*] Downloading result to {output_file}...")
    download_url = f"{base_url}?action=downloadJobResult&jobId={job_id}"
    try:
        response = session.get(download_url, timeout=60)
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
