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

        pf = ProgressFile(input_file, 'rb')
        try:
            files = {'file': (os.path.basename(input_file), pf, 'application/pdf')}
            # Use tuple for (connect, read) timeouts
            response = session.post(f"{base_url}?action=upload", files=files, timeout=(10, 120))
            print() # New line after progress bar
            
            if response.status_code == 200:
                upload_result = response.json()[0]
                break
            else:
                print(f"\033[91m[-] Server returned {response.status_code}. Trying another server...\033[0m")
        except (requests.exceptions.RequestException, TimeoutError) as e:
            print(f"\n\033[93m[!] Server error: {type(e).__name__}. Switching server...\033[0m")
        finally:
            pf.close()
        
        retry_count += 1
        time.sleep(1)

    if not upload_result:
        print(f"\033[91m[!] Failed to upload file after {max_retries} attempts.\033[0m")
        return
        
    print(f"\033[92m[+] Uploaded. Server File ID: {upload_result['file']}\033[0m")

    # --- PHASE 2: START OCR JOB ---
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
