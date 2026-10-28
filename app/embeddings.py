"""Embedding gambar: CLIP jika tersedia, fallback grid RGB (tanpa torch)."""

from __future__ import annotations

import logging
import threading
from io import BytesIO

import numpy as np
from PIL import Image

from app import config

log = logging.getLogger("trash.embeddings")

_clip_lock = threading.Lock()
_clip_model = None
_clip_failed = False


def _fallback_embed(jpeg: bytes) -> list[float]:
    """Vektor ringan dari thumbnail RGB — cukup untuk near-duplicate / warna bentuk kasar."""
    img = Image.open(BytesIO(jpeg)).convert("RGB")
    img = img.resize((32, 32), Image.LANCZOS)
    arr = np.asarray(img, dtype=np.float32).reshape(-1) / 255.0
    # Histogram warna kasar supaya lebih tahan geser kecil
    hist = np.concatenate(
        [np.histogram(arr[i::3], bins=16, range=(0.0, 1.0))[0].astype(np.float32) for i in range(3)]
    )
    hist = hist / (np.linalg.norm(hist) + 1e-9)
    flat = arr / (np.linalg.norm(arr) + 1e-9)
    vec = np.concatenate([flat * 0.7, hist * 0.3])
    vec = vec / (np.linalg.norm(vec) + 1e-9)
    return vec.astype(np.float32).tolist()


def _clip_embed(jpeg: bytes) -> list[float] | None:
    global _clip_model, _clip_failed
    if _clip_failed:
        return None
    with _clip_lock:
        if _clip_failed:
            return None
        try:
            if _clip_model is None:
                from sentence_transformers import SentenceTransformer

                log.info("Memuat CLIP %s …", config.CLIP_MODEL)
                _clip_model = SentenceTransformer(config.CLIP_MODEL)
            img = Image.open(BytesIO(jpeg)).convert("RGB")
            vector = _clip_model.encode(img, convert_to_numpy=True, normalize_embeddings=True)
            return vector.astype(np.float32).tolist()
        except Exception as exc:  # noqa: BLE001
            log.warning("CLIP tidak tersedia, pakai fallback embedding: %s", exc)
            _clip_failed = True
            _clip_model = None
            return None


def embed_image(jpeg: bytes) -> list[float]:
    if config.EMBEDDING_BACKEND == "fallback":
        return _fallback_embed(jpeg)
    if config.EMBEDDING_BACKEND in ("clip", "auto"):
        vector = _clip_embed(jpeg)
        if vector is not None:
            return vector
        if config.EMBEDDING_BACKEND == "clip":
            raise RuntimeError("CLIP diminta tapi gagal dimuat")
    return _fallback_embed(jpeg)


def embedding_backend_name() -> str:
    if config.EMBEDDING_BACKEND == "fallback":
        return "fallback"
    if _clip_failed or config.EMBEDDING_BACKEND == "auto" and _clip_model is None:
        # Belum dicoba: tetap laporkan auto/clip; setelah gagal jadi fallback
        return "fallback" if _clip_failed else config.EMBEDDING_BACKEND
    if _clip_model is not None:
        return "clip"
    return config.EMBEDDING_BACKEND
