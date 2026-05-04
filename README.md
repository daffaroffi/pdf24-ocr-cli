# PDF24 OCR CLI (Headless)

A high-performance, lightweight command-line tool to perform OCR on PDF files using the PDF24 internal API. This tool is written in Rust and operates completely headless, without requiring a webview or browser.

## Features

- **Blazing Fast & Lightweight**: Built with Rust's async/await architecture (tokio & reqwest).
- **Headless Operation**: No browser or webview required, making it perfect for servers and automated scripts.
- **Zero-Copy Streaming Upload**: Handles large PDF files efficiently by streaming bytes directly from disk.
- **Real-time Progress Tracking**: Extracts page-by-page progress information from the API response and displays it via a terminal progress bar (indicatif).
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
3. The binary will be available at ./target/release/pdf24-ocr-cli.

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

## Project Structure

- src/main.rs: The core Rust implementation.
- python_poc/: Contains the original Python Proof of Concept scripts and research files used during development.
- CHANGELOG.md: Detailed history of the project's development from Python prototype to Rust.

## License

This project is for educational and personal use. It interacts with the PDF24 public API. Please respect their terms of service.

---
*Developed as a high-performance alternative to web-based OCR tools.*
