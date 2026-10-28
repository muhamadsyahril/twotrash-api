import os

from dotenv import load_dotenv

load_dotenv()

# Auth untuk client (Pi Zero): kirim header `X-API-Token: <API_TOKEN>`
API_TOKEN_HEADER = "X-API-Token"
API_TOKEN = os.getenv("API_TOKEN", "ganti-token-rahasia-ini")

CATEGORIES = ("organic", "anorganic", "other")

# jev | sumopod | hybrid (Jev dulu, fallback ke Sumopod jika error / confidence rendah)
CLASSIFIER_MODE = os.getenv("CLASSIFIER_MODE", "hybrid").lower()
JEV_MIN_CONFIDENCE = float(os.getenv("JEV_MIN_CONFIDENCE", "0.5"))

TYPESAFE_API_KEY = os.getenv("TYPESAFE_API_KEY", "")
TYPESAFE_BASE_URL = os.getenv("TYPESAFE_BASE_URL", "https://api.typesafe.ai")
TYPESAFE_MODEL = os.getenv("TYPESAFE_MODEL", "jev-latest")

SUMOPOD_API_KEY = os.getenv("SUMOPOD_API_KEY", "")
SUMOPOD_BASE_URL = os.getenv("SUMOPOD_BASE_URL", "https://ai.sumopod.com/v1")
SUMOPOD_MODEL = os.getenv("SUMOPOD_MODEL", "gpt-4o-mini")

HTTP_TIMEOUT = float(os.getenv("HTTP_TIMEOUT", "30"))
MAX_UPLOAD_BYTES = 10 * 1024 * 1024

# Vector memory: simpan gambar + label untuk few-shot / tuning
VECTOR_STORE_ENABLED = os.getenv("VECTOR_STORE_ENABLED", "true").lower() in ("1", "true", "yes")
DATA_DIR = os.getenv("DATA_DIR", "data")
VECTOR_TOP_K = int(os.getenv("VECTOR_TOP_K", "3"))
VECTOR_MIN_SIMILARITY = float(os.getenv("VECTOR_MIN_SIMILARITY", "0.72"))
# fallback = ringan (default, tanpa torch); auto = CLIP jika ada; clip = wajib CLIP
EMBEDDING_BACKEND = os.getenv("EMBEDDING_BACKEND", "fallback").lower()
CLIP_MODEL = os.getenv("CLIP_MODEL", "clip-ViT-B-32")
