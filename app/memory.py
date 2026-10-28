"""Simpan embedding gambar + hasil analisis di ChromaDB untuk few-shot berikutnya."""

from __future__ import annotations

import logging
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from app import config
from app.embeddings import embed_image, embedding_backend_name
from app.prompts import ITEM_CATEGORY

log = logging.getLogger("trash.memory")


@dataclass
class SimilarCase:
    id: str
    item: str
    category: str
    similarity: float
    corrected: bool
    source: str


class VectorMemory:
    def __init__(self) -> None:
        self.enabled = config.VECTOR_STORE_ENABLED
        self._lock = threading.Lock()
        self._collection = None
        self.root = Path(config.DATA_DIR)
        self.images_dir = self.root / "images"
        self.chroma_dir = self.root / "chroma"
        if self.enabled:
            self.images_dir.mkdir(parents=True, exist_ok=True)
            self.chroma_dir.mkdir(parents=True, exist_ok=True)

    def _ensure(self) -> None:
        if not self.enabled:
            raise RuntimeError("Vector store dimatikan")
        if self._collection is not None:
            return
        with self._lock:
            if self._collection is not None:
                return
            import chromadb

            client = chromadb.PersistentClient(path=str(self.chroma_dir))
            self._collection = client.get_or_create_collection(
                name="waste_cases",
                metadata={"hnsw:space": "cosine"},
            )
            log.info(
                "Vector store siap (%s kasus, embedding=%s)",
                self._collection.count(),
                embedding_backend_name(),
            )

    def find_similar(self, jpeg: bytes, top_k: int | None = None) -> tuple[list[float], list[SimilarCase]]:
        if not self.enabled:
            return [], []
        self._ensure()
        embedding = embed_image(jpeg)
        n = self._collection.count()
        if n == 0:
            return embedding, []

        k = min(top_k or config.VECTOR_TOP_K, n)
        result = self._collection.query(
            query_embeddings=[embedding],
            n_results=k,
            include=["metadatas", "distances"],
        )
        cases: list[SimilarCase] = []
        ids = (result.get("ids") or [[]])[0]
        metas = (result.get("metadatas") or [[]])[0]
        dists = (result.get("distances") or [[]])[0]
        for case_id, meta, dist in zip(ids, metas, dists):
            similarity = 1.0 - float(dist)
            if similarity < config.VECTOR_MIN_SIMILARITY:
                continue
            cases.append(
                SimilarCase(
                    id=case_id,
                    item=str(meta.get("item", "")),
                    category=str(meta.get("category", "")),
                    similarity=similarity,
                    corrected=str(meta.get("corrected", "false")).lower() == "true",
                    source=str(meta.get("source", "")),
                )
            )
        return embedding, cases

    def store(
        self,
        jpeg: bytes,
        *,
        item: str,
        category: str,
        confidence: float | None,
        source: str,
        embedding: list[float] | None = None,
        case_id: str | None = None,
        corrected: bool = False,
    ) -> str:
        if not self.enabled:
            return case_id or ""
        self._ensure()
        case_id = case_id or str(uuid.uuid4())
        path = self.images_dir / f"{case_id}.jpg"
        path.write_bytes(jpeg)
        vector = embedding if embedding is not None else embed_image(jpeg)
        meta = {
            "item": item,
            "category": category,
            "source": source,
            "confidence": "" if confidence is None else f"{confidence:.4f}",
            "corrected": "true" if corrected else "false",
            "image_path": str(path),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "embedding_backend": embedding_backend_name(),
        }
        self._collection.upsert(
            ids=[case_id],
            embeddings=[vector],
            metadatas=[meta],
            documents=[f"{category}/{item}"],
        )
        log.info("Tersimpan kasus %s → %s/%s", case_id, category, item)
        return case_id

    def correct(self, case_id: str, item: str) -> dict:
        if item not in ITEM_CATEGORY:
            raise ValueError(f"Item tidak dikenal: {item}")
        if not self.enabled:
            raise RuntimeError("Vector store dimatikan")
        self._ensure()
        existing = self._collection.get(ids=[case_id], include=["metadatas", "embeddings"])
        if not existing["ids"]:
            raise KeyError(case_id)
        meta = dict(existing["metadatas"][0])
        meta["item"] = item
        meta["category"] = ITEM_CATEGORY[item]
        meta["corrected"] = "true"
        meta["corrected_at"] = datetime.now(timezone.utc).isoformat()
        embedding = existing["embeddings"][0]
        if hasattr(embedding, "tolist"):
            embedding = embedding.tolist()
        self._collection.upsert(
            ids=[case_id],
            embeddings=[embedding],
            metadatas=[meta],
            documents=[f"{meta['category']}/{item}"],
        )
        return {"id": case_id, "item": item, "category": meta["category"], "corrected": True}

    def stats(self) -> dict:
        if not self.enabled:
            return {"enabled": False, "count": 0}
        try:
            self._ensure()
            return {
                "enabled": True,
                "count": self._collection.count(),
                "embedding": embedding_backend_name(),
            }
        except Exception as exc:  # noqa: BLE001
            return {"enabled": True, "ready": False, "error": str(exc)}


memory = VectorMemory()
