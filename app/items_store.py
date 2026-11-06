"""Katalog item sampah yang bisa di-CRUD dari admin (tersimpan di data/items.json)."""

from __future__ import annotations

import json
import re
import threading
from pathlib import Path

from app import config
from app.prompts import DEFAULT_ITEM_CATEGORY, DEFAULT_ITEM_CRITERIA

_SLUG_RE = re.compile(r"^[a-z][a-z0-9_]{1,62}$")
_CATEGORIES = ("organic", "anorganic", "other")
_lock = threading.Lock()


class ItemsStore:
    def __init__(self) -> None:
        self.path = Path(config.DATA_DIR) / "items.json"
        self._items: dict[str, dict] = {}
        self.reload()

    def reload(self) -> None:
        with _lock:
            if self.path.is_file():
                raw = json.loads(self.path.read_text(encoding="utf-8"))
                items = {}
                for slug, row in (raw.get("items") or {}).items():
                    items[slug] = {
                        "category": row["category"],
                        "description": row.get("description") or "",
                    }
                self._items = items
            else:
                self._items = {
                    slug: {
                        "category": cat,
                        "description": DEFAULT_ITEM_CRITERIA.get(slug, ""),
                    }
                    for slug, cat in DEFAULT_ITEM_CATEGORY.items()
                }
                self._persist_unlocked()

    def _persist_unlocked(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"items": self._items}
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def all(self) -> dict[str, dict]:
        with _lock:
            return {k: dict(v) for k, v in sorted(self._items.items())}

    def category_map(self) -> dict[str, str]:
        with _lock:
            return {slug: row["category"] for slug, row in self._items.items()}

    def criteria_map(self) -> dict[str, str]:
        with _lock:
            return {slug: row["description"] for slug, row in self._items.items()}

    def list_rows(self, category: str | None = None) -> list[dict]:
        rows = []
        for slug, row in self.all().items():
            if category and row["category"] != category:
                continue
            rows.append({"slug": slug, **row})
        return rows

    def get(self, slug: str) -> dict | None:
        with _lock:
            row = self._items.get(slug)
            return dict(row) if row else None

    def create(self, slug: str, category: str, description: str) -> dict:
        slug = slug.strip().lower()
        category = category.strip().lower()
        description = description.strip()
        if not _SLUG_RE.match(slug):
            raise ValueError("Slug harus snake_case (huruf kecil, angka, underscore)")
        if category not in _CATEGORIES:
            raise ValueError("Kategori tidak valid")
        if not description:
            raise ValueError("Deskripsi wajib diisi")
        with _lock:
            if slug in self._items:
                raise ValueError(f"Item '{slug}' sudah ada")
            self._items[slug] = {"category": category, "description": description}
            self._persist_unlocked()
            return {"slug": slug, **self._items[slug]}

    def update(self, slug: str, category: str, description: str) -> dict:
        category = category.strip().lower()
        description = description.strip()
        if category not in _CATEGORIES:
            raise ValueError("Kategori tidak valid")
        if not description:
            raise ValueError("Deskripsi wajib diisi")
        with _lock:
            if slug not in self._items:
                raise KeyError(slug)
            self._items[slug] = {"category": category, "description": description}
            self._persist_unlocked()
            return {"slug": slug, **self._items[slug]}

    def delete(self, slug: str) -> None:
        with _lock:
            if slug not in self._items:
                raise KeyError(slug)
            if len(self._items) <= 1:
                raise ValueError("Minimal harus ada 1 item")
            del self._items[slug]
            self._persist_unlocked()


items_store = ItemsStore()
