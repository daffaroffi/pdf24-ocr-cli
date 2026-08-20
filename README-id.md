# PDF24 OCR CLI (Headless)

[English](README.md) | [Bahasa Indonesia](README-id.md)

---

Alat baris perintah berperforma tinggi dan ringan untuk melakukan OCR pada file PDF menggunakan API internal PDF24. Alat ini ditulis dalam bahasa Rust dan beroperasi sepenuhnya secara headless, tanpa memerlukan webview atau browser.

## Fitur

- **Cepat & Ringan**: Dibangun dengan arsitektur async/await Rust (tokio & reqwest).
- **Operasi Headless**: Tanpa browser atau webview, cocok untuk server dan skrip otomatis.
- **Upload Streaming Zero-Copy**: Menangani file PDF besar secara efisien dengan streaming byte langsung dari disk.
- **Pelacakan Progres Real-time**: Mengekstrak informasi progres per halaman dari respons API dan menampilkannya melalui progress bar terminal (indicatif).
- **Sistem Fallback Server**: Secara otomatis memilih dan menyeimbangkan request ke cluster server PDF24 (filetools0-29) untuk keandalan maksimal.
- **Dukungan Multibahasa**: Mendukung berbagai bahasa (Indonesia, Inggris, Arab, dll.) dengan memetakan kode ke backend Tesseract server.
- **Force OCR Otomatis**: Memastikan dokumen tetap diproses meskipun lapisan teks sudah terdeteksi.

## Instalasi

Pastikan Rust dan Cargo terinstal di sistem Anda.

1. Clone atau unduh repositori ini.
2. Bangun proyek:
   ```bash
   cargo build --release
   ```
3. Biner tersedia di `./target/release/pdf24-ocr-cli`.

## Penggunaan

```bash
./pdf24-ocr-cli <input_pdf> [kode_bahasa]
```

### Contoh:

- **OCR dalam bahasa Inggris (default)**:
  ```bash
  cargo run -- sample.pdf
  ```

- **OCR dalam bahasa Indonesia**:
  ```bash
  cargo run -- dokumen.pdf id
  ```

- **Cek Versi**:
  ```bash
  ./pdf24-ocr-cli --version
  ```

## Struktur Proyek

- **src/main.rs**: Implementasi inti Rust.
- **python_poc/**: Berisi skrip Python Proof of Concept asli dan file riset yang digunakan selama pengembangan.
- **CHANGELOG.md**: Riwayat detail pengembangan proyek dari prototipe Python hingga Rust.

## Lisensi

Proyek ini untuk penggunaan edukasi dan pribadi. Alat ini berinteraksi dengan API publik PDF24. Harap hormati ketentuan layanan mereka.

---

*Dikembangkan sebagai alternatif berperforma tinggi untuk alat OCR berbasis web.*

---

*[English](README.md)*

---

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
## HTTP API Wrapper

Wrapper HTTP FastAPI tersedia di [`api/`](api/README-id.md). Mengekspos
layanan OCR yang sama sebagai endpoint sync, async, dan batch, dengan
dokumentasi OpenAPI yang auto-generated di `/docs`. Kalau lo mau panggil
OCR dari web app, script, atau service tanpa nge-spawn CLI, lihat
[`api/README-id.md`](api/README-id.md) (atau dalam Bahasa Inggris:
[`api/README.md`](api/README.md)).

