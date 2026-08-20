# PDF24 OCR API

> Part of **[pdf24-ocr-cli](../README.md)**. The parent project is a Rust CLI
> tool for the same OCR service. This subproject adds an HTTP API wrapper
> with sync, async, and batch endpoints. See the main README for the CLI.

> [Bahasa Indonesia](README-id.md) | English

An unofficial, self-hostable HTTP wrapper around [PDF24](https://www.pdf24.org)'s
public OCR service. Accepts PDF files via **multipart upload**, **base64**, or
**URL fetch** and returns a searchable PDF with an embedded text layer.

> **Disclaimer:** This project is **not affiliated with, endorsed by, or
> sponsored by PDF24 GmbH**. It calls the public `client.php` endpoint that
> powers `tools.pdf24.org`, so it can break at any time without warning and
> has no SLA. Use at your own risk and respect PDF24's terms of service.

## Features

- One **sync** endpoint for small files (default < 5 MB, 120 s timeout)
- One **async** endpoint with a job store, progress polling, and TTL cleanup
- **Bearer-token auth** on every endpoint except `/health`
- **Three input modes**: multipart `file`, JSON `file_b64`, JSON `url`

## Quick start

### With Docker Compose (recommended)

```bash
cp .env.example .env
# Edit .env and set API_BEARER_TOKEN to something random.

docker compose up -d --build
curl http://localhost:8000/health
```

Open the interactive docs at <http://localhost:8000/docs>.

### Local (Python 3.10+)

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

All endpoints below require `Authorization: Bearer <API_BEARER_TOKEN>` unless
noted. See the live OpenAPI docs for full request/response schemas and
interactive examples.

| Method | Path | Description |

### Sync example (curl)

```bash
curl -X POST http://localhost:8000/api/v1/ocr/sync \
  -H "Authorization: Bearer $API_BEARER_TOKEN" \
  -F "file=@sample.pdf" \
  -F "lang=id" \
  --output ocr_result.pdf
```

### Async example (curl)

```bash
# Submit
JOB=$(curl -s -X POST http://localhost:8000/api/v1/ocr/async \
  -H "Authorization: Bearer $API_BEARER_TOKEN" \
  -F "file=@big.pdf" \
  -F "lang=en" | jq -r .job_id)

# Poll
curl -H "Authorization: Bearer $API_BEARER_TOKEN" \
  http://localhost:8000/api/v1/ocr/async/$JOB

# Download once status == "done"
curl -H "Authorization: Bearer $API_BEARER_TOKEN" \
  http://localhost:8000/api/v1/ocr/async/$JOB/result \
  --output result.pdf
```

### Base64 and URL inputs

Both sync and async accept JSON instead of multipart:

```json
{ "file_b64": "JVBERi0xLjQK...", "lang": "id" }
```

```json
{ "url": "https://example.com/document.pdf", "lang": "en" }
```

## Configuration

All settings are read from environment variables (or a `.env` file in dev).
See [`.env.example`](.env.example) for the full list with defaults.

| Variable | Default | Notes |
## Architecture

```
client                                  pdf24-ocr-api                            pdf24.org
  |                                           |                                      |
  | POST /api/v1/ocr/sync (multipart)         |                                      |
  |------------------------------------------->|                                      |
  |   Bearer: <token>                         |                                      |
  |                                           | 1. save to TMP_DIR, validate %PDF-   |
|  |                                           |                                      |
```

## Limitations

- **No SLA.** PDF24 can change or block the upstream endpoint at any time.
  Retry behavior is best-effort.
- **In-memory job store.** A server restart loses all running jobs. Suitable
  for single-instance deployments. For multi-instance, swap in Redis.
- **No rate limiting beyond what PDF24 enforces upstream.** If you need
  stricter control, add an API gateway in front.
- **No persistent storage of results.** Results live on disk until the
  job's TTL expires, then they are deleted.

## Development

```bash
pip install -r requirements-dev.txt
pytest                              # run tests
pytest --cov=app --cov-report=term-missing   # with coverage
ruff check .                        # lint
ruff format .                       # format
```

## License

[MIT](LICENSE)
