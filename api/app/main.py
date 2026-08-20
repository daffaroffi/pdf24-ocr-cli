"""FastAPI application entrypoint."""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import __version__
from .config import get_settings
from .routes import health, languages, ocr_async, ocr_batch, ocr_sync
from .services.job_store import init_job_store, shutdown_job_store
from .utils.errors import APIError


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: ensure tmp dir exists and job store is running."""
    settings = get_settings()
    settings.tmp_dir.mkdir(parents=True, exist_ok=True)
    store = init_job_store()
    await store.start()
    yield
    await shutdown_job_store()


settings = get_settings()

app = FastAPI(
    title="PDF24 OCR API",
    version=__version__,
    description=(
        "Unofficial HTTP wrapper around PDF24's public OCR service. "
        "Accepts PDF files via multipart upload, base64, or URL, and returns "
        "searchable PDFs with an embedded text layer. Also supports batch "
        "processing of multiple PDFs in a single request."
    ),
    license_info={"name": "MIT"},
    contact={"name": "PDF24 OCR API", "url": "https://github.com/yourname/pdf24-ocr-cli"},
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=False,
)


@app.exception_handler(APIError)
async def api_error_handler(_request: Request, exc: APIError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content=exc.to_dict())


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "error": "validation_error",
            "message": "Request validation failed",
            "detail": exc.errors(),
        },
    )


@app.get("/")
def root() -> dict:
    return {
        "app": "PDF24 OCR API",
        "version": __version__,
        "docs": "/docs",
        "redoc": "/redoc",
        "health": "/health",
    }


app.include_router(ocr_sync.router)
app.include_router(ocr_async.router)
app.include_router(ocr_batch.router)
app.include_router(languages.router)
app.include_router(health.router)
    contact={"name": "PDF24 OCR API", "url": "https://github.com/daffaroffi/pdf24-ocr-cli"},
