# -*- coding: utf-8 -*-
"""Централизованная конфигурация KOIB RAG."""
from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

APP_NAME = "KOIB RAG API"
APP_VERSION = os.getenv("KOIB_VERSION", "4.11.0")

BASE_DIR = Path(__file__).parent.resolve()
DATA_DIR = BASE_DIR / "data"
DOCS_DIR = Path(os.getenv("KOIB_DOCS_DIR", str(DATA_DIR / "docs"))).expanduser()
ARTIFACTS_DIR = Path(os.getenv("KOIB_ARTIFACTS_DIR", str(DATA_DIR / "artifacts"))).expanduser()
OUTPUT_DIR = Path(os.getenv("KOIB_OUTPUT_DIR", str(BASE_DIR / "output"))).expanduser()
INDEX_DIR = OUTPUT_DIR / "index"
DOCSTORE_DIR = OUTPUT_DIR / "docstore"
FIGURES_DIR = OUTPUT_DIR / "figures"
LOGS_DIR = OUTPUT_DIR / "logs"
METADATA_DIR = OUTPUT_DIR / "metadata"

# LLM providers: gigachat | openai | local
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gigachat").lower().strip()
EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "local").lower().strip()

LOCAL_EMBEDDING_MODEL = os.getenv("LOCAL_EMBEDDING_MODEL", "intfloat/multilingual-e5-small")
OPENAI_EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
PASSAGE_PREFIX = os.getenv("PASSAGE_PREFIX", "passage: ")
QUERY_PREFIX = os.getenv("QUERY_PREFIX", "query: ")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

TEXT_CHUNK_SIZE = int(os.getenv("TEXT_CHUNK_SIZE", "800"))
TEXT_CHUNK_OVERLAP = int(os.getenv("TEXT_CHUNK_OVERLAP", "80"))
MIN_CHUNK_LENGTH = int(os.getenv("MIN_CHUNK_LENGTH", "50"))

VECTOR_SEARCH_K = int(os.getenv("VECTOR_SEARCH_K", "15"))
BM25_SEARCH_K = int(os.getenv("BM25_SEARCH_K", "10"))
FINAL_TOP_K = int(os.getenv("FINAL_TOP_K", "4"))
HYBRID_ALPHA = float(os.getenv("HYBRID_ALPHA", "0.6"))

USE_RERANKER = os.getenv("USE_RERANKER", "false").lower() == "true"
RERANKER_MODEL = os.getenv("RERANKER_MODEL", "DiTy/ru-reranker-base")
USE_ONNX_RERANKER = os.getenv("USE_ONNX_RERANKER", "false").lower() == "true"
USE_HYDE = os.getenv("USE_HYDE", "false").lower() == "true"
BM25_USE_STOPWORDS = os.getenv("BM25_USE_STOPWORDS", "true").lower() == "true"
BM25_USE_LEMMATIZATION = os.getenv("BM25_USE_LEMMATIZATION", "true").lower() == "true"

GIGACHAT_CREDENTIALS = os.getenv("GIGACHAT_CREDENTIALS", "")
GIGACHAT_MODEL = os.getenv("GIGACHAT_MODEL", "GigaChat")
GIGACHAT_SCOPE = os.getenv("GIGACHAT_SCOPE", "GIGACHAT_API_PERS")
GIGACHAT_TEMPERATURE = float(os.getenv("GIGACHAT_TEMPERATURE", "0.2"))
GIGACHAT_MAX_TOKENS = int(os.getenv("GIGACHAT_MAX_TOKENS", "1536"))
GIGACHAT_TIMEOUT = int(os.getenv("GIGACHAT_TIMEOUT", "45"))
GIGACHAT_VERIFY_SSL = os.getenv("GIGACHAT_VERIFY_SSL", "false").lower() == "true"

OPENAI_LLM_MODEL = os.getenv("OPENAI_LLM_MODEL", "gpt-4o-mini")
OPENAI_TEMPERATURE = float(os.getenv("OPENAI_TEMPERATURE", "0.2"))
OPENAI_MAX_TOKENS = int(os.getenv("OPENAI_MAX_TOKENS", "1536"))

LOCAL_LLM_MODEL = os.getenv("LOCAL_LLM_MODEL", "IlyaGusev/saiga_mistral_7b")
LOCAL_LLM_URL = os.getenv("LOCAL_LLM_URL", "http://localhost:11434").rstrip("/")

VALIDATION_IGNORE_QUOTES = os.getenv("VALIDATION_IGNORE_QUOTES", "true").lower() == "true"
UNCERTAINTY_MIN_LENGTH = int(os.getenv("UNCERTAINTY_MIN_LENGTH", "50"))
VALIDATION_USE_LLM_JUDGE = os.getenv("VALIDATION_USE_LLM_JUDGE", "false").lower() == "true"
VALIDATION_CHECK_CITATIONS = os.getenv("VALIDATION_CHECK_CITATIONS", "true").lower() == "true"

OCR_DPI = int(os.getenv("OCR_DPI", "150"))
OCR_MIN_TEXT_CHARS = int(os.getenv("OCR_MIN_TEXT_CHARS", "50"))
MIN_IMAGE_WIDTH = int(os.getenv("MIN_IMAGE_WIDTH", "80"))
MIN_IMAGE_HEIGHT = int(os.getenv("MIN_IMAGE_HEIGHT", "80"))
PARSING_ENGINE = os.getenv("PARSING_ENGINE", "pymupdf")
ARTIFACT_ALLOW_BM25_FALLBACK = os.getenv("ARTIFACT_ALLOW_BM25_FALLBACK", "false").lower() == "true"
ARTIFACT_MIN_CONTENT_CHARS = int(os.getenv("ARTIFACT_MIN_CONTENT_CHARS", "30"))

API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", "8000"))

VK_CONFIRM_CODE = os.getenv("VK_CONFIRM_CODE", "12345678")
VK_GROUP_ID = os.getenv("VK_GROUP_ID", "")
VK_ACCESS_TOKEN = os.getenv("VK_ACCESS_TOKEN", "")
VK_SECRET_KEY = os.getenv("VK_SECRET_KEY", "")
VK_API_VERSION = os.getenv("VK_API_VERSION", "5.131")
VK_RATE_LIMIT_PER_MINUTE = int(os.getenv("VK_RATE_LIMIT_PER_MINUTE", "20"))
VK_GLOBAL_RATE_LIMIT_PER_MINUTE = int(os.getenv("VK_GLOBAL_RATE_LIMIT_PER_MINUTE", "120"))
VK_MAX_INCOMING_CHARS = int(os.getenv("VK_MAX_INCOMING_CHARS", "1500"))
VK_MAX_OUTGOING_CHARS = int(os.getenv("VK_MAX_OUTGOING_CHARS", "3900"))
VK_OUTBOUND_TIMEOUT = int(os.getenv("VK_OUTBOUND_TIMEOUT", "10"))
VK_DEDUP_TTL_SECONDS = int(os.getenv("VK_DEDUP_TTL_SECONDS", "86400"))
VK_SEND_TYPING = os.getenv("VK_SEND_TYPING", "true").lower() == "true"
VK_REPLY_IN_GROUP_CHATS = os.getenv("VK_REPLY_IN_GROUP_CHATS", "false").lower() == "true"
VK_BOT_MENTION_ALIASES = [
    alias.strip().lower()
    for alias in os.getenv("VK_BOT_MENTION_ALIASES", "коиб,koib").split(",")
    if alias.strip()
]
VK_ADMIN_IDS = {
    item.strip()
    for item in os.getenv("VK_ADMIN_IDS", "").split(",")
    if item.strip()
}
VK_ERROR_MESSAGE = os.getenv(
    "VK_ERROR_MESSAGE",
    "Не удалось подготовить ответ. Проверьте подключение к серверу и при необходимости обратитесь к администратору системы.",
)
PROCEDURAL_REMINDER_ENABLED = os.getenv("PROCEDURAL_REMINDER_ENABLED", "true").lower() == "true"

SEMANTIC_CACHE_ENABLED = os.getenv("SEMANTIC_CACHE_ENABLED", "true").lower() == "true"
SEMANTIC_CACHE_THRESHOLD = float(os.getenv("SEMANTIC_CACHE_THRESHOLD", "0.92"))
SEMANTIC_CACHE_MAX_CANDIDATES = int(os.getenv("SEMANTIC_CACHE_MAX_CANDIDATES", "1000"))

MAX_CONCURRENT_GENERATIONS = int(os.getenv("MAX_CONCURRENT_GENERATIONS", "2"))
MAX_TABLE_ROWS_IN_PROMPT = int(os.getenv("MAX_TABLE_ROWS_IN_PROMPT", "30"))
MAX_TABLE_TOKENS_IN_PROMPT = int(os.getenv("MAX_TABLE_TOKENS_IN_PROMPT", "1500"))
USE_USHAPED_CONTEXT = os.getenv("USE_USHAPED_CONTEXT", "true").lower() == "true"

INDEXING_BATCH_SIZE = int(os.getenv("INDEXING_BATCH_SIZE", "64"))
INDEXING_FLUSH_THRESHOLD = int(os.getenv("INDEXING_FLUSH_THRESHOLD", "2000"))
INDEXING_DEVICE = os.getenv("INDEXING_DEVICE", "cpu").lower().strip()
INGEST_MAX_WORKERS = int(os.getenv("INGEST_MAX_WORKERS", "0"))
HF_OFFLINE_MODE = os.getenv("HF_OFFLINE_MODE", "false").lower() == "true"


def get_device() -> str:
    """Определить устройство для embedding-модели."""
    if INDEXING_DEVICE != "auto":
        return INDEXING_DEVICE
    try:
        import torch
        return "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:
        return "cpu"


def ensure_dirs() -> None:
    for d in [DOCS_DIR, ARTIFACTS_DIR, OUTPUT_DIR, INDEX_DIR, DOCSTORE_DIR, FIGURES_DIR, LOGS_DIR, METADATA_DIR]:
        d.mkdir(parents=True, exist_ok=True)
