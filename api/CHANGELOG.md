# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project
adheres to [Semantic Versioning](https://semver.org/).

## [0.1.0] - 2026-XX-XX

### Added
- FastAPI application wrapping PDF24's public OCR service
- Bearer-token authentication for all non-health endpoints
- `POST /api/v1/ocr/sync` - synchronous OCR, returns the PDF inline
- `POST /api/v1/ocr/async` - asynchronous OCR, returns a `job_id`
- `GET /api/v1/ocr/async/{job_id}` - poll job status and progress
- `GET /api/v1/ocr/async/{job_id}/result` - download the result PDF
- `GET /api/v1/languages` - list of supported language shortcuts
- `GET /health` - liveness check with cached upstream reachability probe
- Three input formats: multipart upload, base64, and URL fetch
- In-memory job store with TTL-based cleanup
- Server fallback: each retry picks a new random PDF24 cluster server
- Language code mapping: `id` -> `ind`, `en` -> `eng`, `ar` -> `ara`
- Pytest suite with respx-based HTTP mocking (82% coverage)
- Multi-stage Dockerfile and `docker-compose.yml` for self-hosting
- OpenAPI documentation at `/docs` and `/redoc`

## [0.2.0] - 2026-XX-XX

### Added
- `POST /api/v1/ocr/batch-async` - queue a batch of PDFs, returns 202 + `job_id`
- Bounded-concurrency parallel OCR (default 3 at a time, configurable)
- Per-file progress tracking via the `batch` field in job status responses
- Per-file failure isolation: one bad file does not abort the batch
- ZIP output containing one `ocr_<original>.pdf` per successful file
  plus a `results.json` summary with per-file status and error messages
- The existing `/async/{job_id}/result` endpoint now returns a ZIP
  for batch jobs (auto-detected via the `is_batch` job flag)
- New env vars: `BATCH_MAX_FILES`, `BATCH_MAX_TOTAL_SIZE_MB`, `BATCH_CONCURRENCY`

### Changed
- Extended `JobInfo` with optional batch fields (`is_batch`, `total_files`,
  `files_completed`, `files_failed`, `current_file`, `file_results`)
- Added `PACKAGING` job status for the final ZIP-creation step
