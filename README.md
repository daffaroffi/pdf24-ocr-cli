<h1 align="center">PDF24 OCR CLI (Headless)</h1>

<p align="center">
  <img src="https://img.shields.io/badge/Rust-000000?style=for-the-badge&logo=rust&logoColor=white" alt="Rust">
  <img src="https://img.shields.io/badge/Platform-Linux%20%7C%20Windows%20%7C%20Android-orange?style=for-the-badge" alt="Platform">
  <img src="https://img.shields.io/badge/UX-Modern%20CLI%20%7C%20GUI-blue?style=for-the-badge" alt="UX">
  <img src="https://img.shields.io/badge/Status-v1.0.0-success?style=for-the-badge" alt="Status">
</p>

<p align="center">
  <a href="https://saweria.co/fyodordostoevsky">
    <img src="https://img.shields.io/badge/Support_Me-Saweria-ff8800?style=for-the-badge&logo=buymeacoffee&logoColor=white" alt="Support" />
  </a>
  <a href="https://codeberg.org/lyraaa/Online-OCR-With-No-Webview/releases/tag/v1.0.0">
    <img src="https://img.shields.io/badge/Download-Latest_Release-success?style=for-the-badge&logo=codeberg&logoColor=white" alt="Download" />
  </a>
</p>

A high-performance, lightweight command-line tool to perform OCR on PDF files using the PDF24 internal API. This tool is written in Rust and operates completely headless, without requiring a webview or browser.

## Features

- **Blazing Fast & Lightweight**: Built with Rust's async/await architecture (tokio & reqwest).
- **Headless Operation**: No browser or webview required, making it perfect for servers and automated scripts.
- **Zero-Copy Streaming Upload**: Handles large PDF files efficiently by streaming bytes directly from disk.
- **Real-time Progress Tracking**: Extracts page-by-page progress information from the API response and displays it via a beautiful terminal progress bar (indicatif).
- **Server Fallback System**: Automatically selects and balances requests across the PDF24 server cluster (filetools0-29) for maximum reliability.
- **Multi-language Support**: Supports various languages (Indonesian, English, Arabic, etc.) by mapping codes to the server's Tesseract backend.
- **Automatic Force OCR**: Ensures documents are processed even if a text layer is already detected.

## Installation

Ensure you have Rust and Cargo installed on your system.

1. Clone or download this repository.
2. Build the project:
   ```bash
   cargo build --release
   ```
3. The binary will be available at `./target/release/pdf24-ocr-cli`.

## Usage

```bash
./pdf24-ocr-cli <input_pdf> [language_code]
```

### Examples:

- **OCR in English (default)**:
  ```bash
  cargo run -- sample.pdf
  ```

- **OCR in Indonesian**:
  ```bash
  cargo run -- dokumen.pdf id
  ```

- **Check Version**:
  ```bash
  ./pdf24-ocr-cli --version
  ```

## Project Structure

- **src/main.rs**: The core Rust implementation.
- **python_poc/**: Contains the original Python Proof of Concept scripts and research files used during development.
- **CHANGELOG.md**: Detailed history of the project's development from Python prototype to Rust.

## License

This project is for educational and personal use. It interacts with the PDF24 public API. Please respect their terms of service.

---
*Developed as a high-performance alternative to web-based OCR tools.*

## HTTP API Wrapper

A FastAPI HTTP wrapper is available in [`api/`](api/README.md). It exposes
the same OCR service as sync, async, and batch endpoints, with OpenAPI
docs auto-generated at `/docs`. If you want to call OCR from a web app,
script, or service without spawning the CLI, see
[`api/README.md`](api/README.md) (or in Bahasa Indonesia:
[`api/README-id.md`](api/README-id.md)).
