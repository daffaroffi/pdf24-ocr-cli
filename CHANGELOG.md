# Changelog - Online OCR (PoC & Prototype)

Project ini adalah fase Proof of Concept (PoC) untuk memetakan alur API internal PDF24. Seluruh logika di sini digunakan sebagai acuan implementasi final menggunakan bahasa Rust.

## [v1.0.0] - 2026-05-04 (Stable Rust Release)

### Added
- **Full Rust Migration**: Implementasi ulang seluruh logika dari Python ke Rust untuk performa dan keamanan tipe data.
- **Persistent Cookie Store**: Penanganan session otomatis menggunakan `reqwest::Client` dengan cookie store, memperbaiki masalah "Forbidden access".
- **Advanced Metadata Handling**: Penggunaan JSON dinamis untuk metadata file upload guna memastikan kompatibilitas penuh dengan API PDF24.
- **Enhanced Progress Bars**: Penambahan progress bar untuk proses Download dan perbaikan sinkronisasi spinner pada proses OCR.
- **Robust Error Handling**: Implementasi `anyhow` dan `Context` untuk pesan error yang lebih informatif.

## [v0.1.0-prototype] - 2026-05-04 (Python PoC Phase)

### Added
- **Dynamic OCR Progress Bar**: Implementasi sistem pelacakan progres berbasis halaman (page X of Y) yang diekstrak langsung dari respon API menggunakan Regex.
- **Improved UI Terminal**: Menggunakan ANSI escape codes (\033[K) untuk line clearing agar progress bar tetap berada di satu baris dan tidak merusak tampilan terminal.
- **Force OCR Logic**: Penambahan flag forceOcr: True untuk memaksa API memproses dokumen meskipun lapisan teks sudah terdeteksi (menghindari skip otomatis oleh server).
- **Advanced Language Mapping**: Pemetaan kode bahasa ISO 2-karakter ke standar 3-karakter Tesseract (contoh: id -> ind, en -> eng).
- **Streaming Upload Engine**: Penggunaan http.client untuk mengunggah file besar secara chunked guna menghindari memory error dan timeout pada koneksi lambat.
- **Server Fallback System**: Logika pemilihan server acak dari klaster filetools0.pdf24.org hingga filetools29.pdf24.org untuk meningkatkan tingkat keberhasilan request.
- **Automated Download**: Sistem penanganan otomatis hasil jadi (output PDF) setelah status pekerjaan dinyatakan done.

### Changed
- Migrasi dari polling status sederhana (Spinner) ke estimated/parsed progress bar yang lebih informatif.
- Optimasi timeout upload hingga 300 detik untuk mendukung file PDF berukuran besar (>25MB).

### Fixed
- Memperbaiki masalah static progress di mana baris baru tercipta setiap kali status diperbarui (sekarang menggunakan overwriting satu baris).
- Memperbaiki kegagalan job akibat API yang tidak memproses dokumen dengan teks minimal.

---
*Dokumentasi ini dibuat sebagai bagian dari sesi pengembangan prototipe.*
