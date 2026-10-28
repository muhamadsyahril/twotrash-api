import hmac
import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field

from app import config
from app.classifiers import ClassifierError, classify
from app.image_utils import InvalidImageError, prepare_jpeg
from app.memory import memory
from app.prompts import ITEM_CATEGORY

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("trash.api")

token_header = APIKeyHeader(name=config.API_TOKEN_HEADER, auto_error=False)


def require_token(token: str | None = Depends(token_header)) -> None:
    if not token or not hmac.compare_digest(token, config.API_TOKEN):
        raise HTTPException(status_code=401, detail="Token tidak valid")


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.http = httpx.AsyncClient(timeout=config.HTTP_TIMEOUT)
    yield
    await app.state.http.aclose()


app = FastAPI(title="Trash Sorter Bridge", lifespan=lifespan)


class FeedbackBody(BaseModel):
    id: str = Field(..., description="ID kasus dari response /classify")
    item: str = Field(..., description="Slug item yang benar, mis. kaleng_minuman")


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "mode": config.CLASSIFIER_MODE,
        "memory": memory.stats(),
    }


@app.post("/classify", dependencies=[Depends(require_token)])
async def classify_image(request: Request, image: UploadFile | None = File(None)):
    raw = await image.read() if image is not None else await request.body()
    if not raw:
        raise HTTPException(status_code=400, detail="Gambar kosong")
    if len(raw) > config.MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Gambar terlalu besar")

    try:
        jpeg = prepare_jpeg(raw)
    except InvalidImageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    embedding: list[float] = []
    similar = []
    if config.VECTOR_STORE_ENABLED:
        try:
            embedding, similar = memory.find_similar(jpeg)
            if similar:
                log.info(
                    "Few-shot dari %s kasus mirip: %s",
                    len(similar),
                    ", ".join(f"{s.item}@{s.similarity:.2f}" for s in similar),
                )
        except Exception as exc:  # noqa: BLE001 — klasifikasi tetap jalan tanpa memory
            log.warning("Pencarian vector gagal, lanjut tanpa few-shot: %s", exc)

    try:
        result = await classify(request.app.state.http, jpeg, similar)
    except ClassifierError as exc:
        log.error("Klasifikasi gagal: %s", exc)
        raise HTTPException(status_code=502, detail="Gagal mengklasifikasi gambar") from exc

    if config.VECTOR_STORE_ENABLED:
        try:
            result.id = memory.store(
                jpeg,
                item=result.item,
                category=result.category,
                confidence=result.confidence,
                source=result.source,
                embedding=embedding or None,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("Gagal menyimpan ke vector store: %s", exc)

    log.info(
        "Hasil: %s/%s (source=%s, confidence=%s, id=%s)",
        result.category,
        result.item,
        result.source,
        result.confidence,
        result.id,
    )
    return result.as_response()


@app.post("/feedback", dependencies=[Depends(require_token)])
async def feedback(body: FeedbackBody):
    """Koreksi label kasus tersimpan — dipakai untuk tuning few-shot berikutnya."""
    item = body.item.lower().strip()
    if item not in ITEM_CATEGORY:
        raise HTTPException(status_code=400, detail=f"Item tidak dikenal: {item}")
    try:
        return memory.correct(body.id, item)
    except KeyError:
        raise HTTPException(status_code=404, detail="Kasus tidak ditemukan") from None
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
