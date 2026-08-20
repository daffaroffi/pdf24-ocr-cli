# PDF24 OCR API

> Bagian dari **[pdf24-ocr-cli](../README-id.md)**. Project utama adalah
> tool CLI Rust untuk layanan OCR yang sama. Subproject ini menambahkan
> wrapper HTTP API dengan endpoint sync, async, dan batch. Lihat README
> utama untuk versi CLI-nya.

> English | [Bahasa Indonesia](README-id.md)

Wrapper HTTP tidak resmi dan bisa di-host sendiri di atas layanan OCR publik
[PDF24](https://www.pdf24.org). Menerima file PDF lewat **multipart upload**,
**base64**, atau **URL fetch**, dan mengembalikan PDF searchable dengan
lapisan teks tertanam.

> **Disclaimer:** Project ini **bukan berafiliasi dengan, didukung oleh,
> atau disponsori oleh PDF24 GmbH**. Tool ini memanggil endpoint `client.php`
> publik yang menjalankan `tools.pdf24.org`, sehingga bisa rusak sewaktu-waktu
> tanpa pemberitahuan dan tidak ada SLA. Gunakan dengan risiko sendiri dan
> hormati terms of service PDF24.

## Fitur

- Satu endpoint **sync** untuk file kecil (default < 5 MB, timeout 120 detik)
- Satu endpoint **async** dengan job store, polling progress, dan TTL cleanup
  untuk file besar (default < 100 MB)
- **Bearer-token auth** di semua endpoint kecuali `/health`
- **Tiga mode input**: multipart `file`, JSON `file_b64`, JSON `url`
- **Server fallback** di client PDF24: tiap retry pilih server acak baru dari
  cluster `filetools0..29`
- **OpenAPI 3.1** auto-generated di `/docs` (Swagger UI) dan `/redoc`
- **Error response terstruktur** dengan kode (`file_too_large`, `invalid_file`,
  `pdf24_error`, `pdf24_timeout`, `job_not_found`, `job_not_ready`, ...)
- **Multi-stage Docker image** dan `docker-compose.yml` untuk self-hosting
- **Test suite** dengan mock HTTP berbasis respx (23 test, coverage 82%)

## Quick Start

### Dengan Docker Compose (direkomendasikan)

```bash
cp .env.example .env
# Edit .env dan set API_BEARER_TOKEN dengan string acak.

docker compose up -d --build
curl http://localhost:8000/health
```

Buka docs interaktif di <http://localhost:8000/docs>.

### Lokal (Python 3.10+)

```bash
python -m venv .venv
.venv\Scripts\activate       # Windows
# source .venv/bin/activate  # macOS / Linux

pip install -r requirements-dev.txt
cp .env.example .env
set API_BEARER_TOKEN=change-me     # Windows
# export API_BEARER_TOKEN=change-me  # macOS / Linux

uvicorn app.main:app --reload --port 8000
```

## API

Semua endpoint di bawah butuh `Authorization: Bearer <API_BEARER_TOKEN>` kecuali
disebutkan. Lihat OpenAPI docs live untuk schema request/response lengkap
dan contoh interaktif.

| Method | Path | Deskripsi |

### Contoh sync (curl)

```bash
curl -X POST http://localhost:8000/api/v1/ocr/sync \
  -H "Authorization: Bearer $API_BEARER_TOKEN" \
  -F "file=@sample.pdf" \
  -F "lang=id" \
  --output ocr_result.pdf
```

### Contoh async (curl)

```bash
# Submit
JOB=$(curl -s -X POST http://localhost:8000/api/v1/ocr/async \
  -H "Authorization: Bearer $API_BEARER_TOKEN" \
  -F "file=@big.pdf" \
  -F "lang=en" | jq -r .job_id)

# Poll
curl -H "Authorization: Bearer $API_BEARER_TOKEN" \
  http://localhost:8000/api/v1/ocr/async/$JOB

# Download setelah status == "done"
curl -H "Authorization: Bearer $API_BEARER_TOKEN" \
  http://localhost:8000/api/v1/ocr/async/$JOB/result \
  --output result.pdf
```

### Input base64 dan URL

Baik sync maupun async menerima JSON代替 multipart:

```json
{ "file_b64": "JVBERi0xLjQK...", "lang": "id" }
```

```json
{ "url": "https://example.com/document.pdf", "lang": "en" }
```

## Konfigurasi

Semua setting dibaca dari environment variable (atau file `.env` saat
development). Lihat [`.env.example`](.env.example) untuk daftar lengkap
dengan default.

| Variable | Default | Catatan |
## Arsitektur

```
client                                  pdf24-ocr-api                            pdf24.org
  |                                           |                                      |
  | POST /api/v1/ocr/sync (multipart)         |                                      |
  |------------------------------------------->|                                      |
  |   Bearer: <token>                         |                                      |
  |                                           | 1. simpan ke TMP_DIR, validasi %PDF- |
|  |                                           |                                      |
```

## Keterbatasan

- **Tanpa SLA.** PDF24 bisa mengubah atau memblokir endpoint upstream kapan
  saja. Perilaku retry adalah best-effort.
- **Job store in-memory.** Restart server akan menghilangkan semua job yang
  sedang berjalan. Cocok untuk deployment single-instance. Untuk multi-
  instance, ganti dengan Redis.
- **Tidak ada rate limiting** selain yang PDF24 enforce di upstream. Kalau
  butuh kontrol lebih ketat, tambahkan API gateway di depan.
- **Hasil tidak disimpan permanen.** Hasil hidup di disk sampai TTL job
  expire, lalu dihapus.

## Development

```bash
pip install -r requirements-dev.txt
pytest                              # jalankan test
pytest --cov=app --cov-report=term-missing   # dengan coverage
ruff check .                        # lint
ruff format .                       # format
```

## Lisensi

[MIT](LICENSE)
