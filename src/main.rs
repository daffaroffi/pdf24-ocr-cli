use anyhow::{anyhow, Context, Result};
use futures_util::StreamExt;
use indicatif::{ProgressBar, ProgressStyle};
use rand::Rng;
use regex::Regex;
use reqwest::{multipart, Client};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::path::Path;
use std::time::Duration;
use tokio::fs::File;
use tokio::io::AsyncWriteExt;
use tokio_util::io::ReaderStream;

#[derive(Debug, Serialize, Deserialize)]
struct UploadResult {
    file: String,
    #[serde(rename = "size")]
    size: u64,
}

#[derive(Debug, Serialize, Deserialize)]
struct JobResult {
    #[serde(rename = "jobId")]
    job_id: String,
}

#[derive(Debug, Serialize, Deserialize)]
struct StatusResult {
    #[serde(default)]
    status: String,
    job: Option<serde_json::Value>,
    error: Option<String>,
}

struct OcrConfig {
    base_url: String,
    client: Client,
    lang_map: HashMap<&'static str, &'static str>,
}

impl OcrConfig {
    fn new() -> Self {
        let mut lang_map = HashMap::new();
        lang_map.insert("id", "ind");
        lang_map.insert("en", "eng");
        lang_map.insert("ar", "ara");

        let mut headers = reqwest::header::HeaderMap::new();
        headers.insert("Origin", "https://tools.pdf24.org".parse().unwrap());
        headers.insert("Referer", "https://tools.pdf24.org/en/ocr-pdf".parse().unwrap());

        let client = Client::builder()
            .user_agent("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
            .default_headers(headers)
            .build()
            .unwrap();

        let server_num = rand::thread_rng().gen_range(0..30);
        let base_url = format!("https://filetools{}.pdf24.org/client.php", server_num);

        Self { base_url, client, lang_map }
    }

    fn get_tesseract_lang(&self, lang: &str) -> String {
        self.lang_map.get(lang).map(|&s| s.to_string()).unwrap_or_else(|| lang.to_string())
    }
}

async fn upload_file(config: &OcrConfig, file_path: &Path) -> Result<UploadResult> {
    let file = File::open(file_path).await.context("Failed to open file")?;
    let metadata = file.metadata().await?;
    let file_size = metadata.len();
    let filename = file_path.file_name().and_then(|n| n.to_str()).unwrap_or("file.pdf").to_string();

    println!("[*] Uploading: {} ({:.2} MB)", filename, file_size as f64 / 1_048_576.0);
    
    let pb = ProgressBar::new(file_size);
    pb.set_style(ProgressStyle::default_bar()
        .template("{spinner:.green} [{elapsed_precise}] [{bar:40.cyan/blue}] {bytes}/{total_bytes} ({eta})")?
        .progress_chars("#>-"));

    let stream = ReaderStream::new(file).map(move |item| {
        if let Ok(ref chunk) = item {
            pb.inc(chunk.len() as u64);
        }
        item
    });

    let part = multipart::Part::stream(reqwest::Body::wrap_stream(stream))
        .file_name(filename)
        .mime_str("application/pdf")?;

    let form = multipart::Form::new().part("file", part);

    let url = format!("{}?action=upload", config.base_url);
    let resp = config.client.post(url)
        .multipart(form)
        .send()
        .await?;

    if !resp.status().is_success() {
        return Err(anyhow!("Upload failed with status: {}", resp.status()));
    }

    let results: Vec<UploadResult> = resp.json().await?;
    let res = results.into_iter().next().ok_or_else(|| anyhow!("No upload result in response"))?;
    
    println!("\n[+] Uploaded. File ID: {}", res.file);
    Ok(res)
}

async fn start_ocr_job(config: &OcrConfig, upload_res: UploadResult, lang: &str) -> Result<String> {
    let tesseract_lang = config.get_tesseract_lang(lang);
    println!("[*] Starting OCR job (lang={})...", tesseract_lang);

    let payload = serde_json::json!({
        "files": [upload_res],
        "langCode": tesseract_lang,
        "outputType": "pdf",
        "removeBackground": false,
        "rotatePages": false,
        "deskew": false,
        "clean": false,
        "forceOcr": true,
        "joinFiles": false
    });

    let url = format!("{}?action=ocrPdf", config.base_url);
    let resp = config.client.post(url)
        .json(&payload)
        .send()
        .await?;

    let res: JobResult = resp.json().await?;
    println!("[+] Job started. Job ID: {}", res.job_id);
    Ok(res.job_id)
}

async fn poll_status(config: &OcrConfig, job_id: &str) -> Result<()> {
    let pb = ProgressBar::new(100);
    pb.set_style(ProgressStyle::default_bar()
        .template("{spinner:.green} [*] Processing OCR [{bar:40.cyan/blue}] {percent}% {msg}")?
        .progress_chars("#>-"));
    
    pb.set_message("Initializing...");
    pb.enable_steady_tick(Duration::from_millis(100));

    let re_page = Regex::new(r"page (\d+) of (\d+)")?;
    let url = format!("{}?action=getStatus", config.base_url);

    loop {
        let payload = serde_json::json!({ "jobId": job_id });
        let resp = config.client.post(&url)
            .json(&payload)
            .send()
            .await?;

        let text = resp.text().await?;
        // println!("\nDEBUG RESPONSE: {}", text); 

        let res: StatusResult = serde_json::from_str(&text).context(format!("Failed to parse JSON: {}", text))?;

        if res.status == "done" {
            pb.set_position(100);
            pb.finish_with_message("Complete!");
            break;
        } else if res.status == "error" {
            return Err(anyhow!("OCR failed: {}", res.error.unwrap_or_default()));
        }

        if let Some(job) = res.job {
            if let Some(msg) = job.get("progress.msg").and_then(|m| m.as_str()) {
                pb.set_message(msg.to_string());
                if let Some(caps) = re_page.captures(msg) {
                    let current = caps[1].parse::<u64>().unwrap_or(0);
                    let total = caps[2].parse::<u64>().unwrap_or(100);
                    pb.set_length(total);
                    pb.set_position(current);
                }
            }
        }

        tokio::time::sleep(Duration::from_secs(2)).await;
    }

    Ok(())
}

async fn download_result(config: &OcrConfig, job_id: &str, output_path: &str) -> Result<()> {
    println!("[*] Downloading result to {}...", output_path);
    let url = format!("{}?action=downloadJobResult&jobId={}", config.base_url, job_id);
    
    let mut resp = config.client.get(url).send().await?;
    if !resp.status().is_success() {
        return Err(anyhow!("Download failed with status: {}", resp.status()));
    }

    let mut file = File::create(output_path).await?;
    while let Some(chunk) = resp.chunk().await? {
        file.write_all(&chunk).await?;
    }

    println!("[+] Success! File saved as {}", output_path);
    Ok(())
}

#[tokio::main]
async fn main() -> Result<()> {
    let args: Vec<String> = std::env::args().collect();
    if args.len() < 2 {
        println!("Usage: {} <input_pdf> [lang]", args[0]);
        return Ok(());
    }

    let input_path = &args[1];
    let lang = if args.len() > 2 { &args[2] } else { "en" };
    let output_path = format!("ocr_result_{}", Path::new(input_path).file_name().unwrap().to_str().unwrap());

    let config = OcrConfig::new();
    println!("[*] Using server: {}", config.base_url);

    let upload_res = upload_file(&config, Path::new(input_path)).await?;
    let job_id = start_ocr_job(&config, upload_res, lang).await?;
    poll_status(&config, &job_id).await?;
    download_result(&config, &job_id, &output_path).await?;

    Ok(())
}
