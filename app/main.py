import hmac
import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.security import APIKeyHeader

from app import config
from app.classifiers import ClassifierError, classify
from app.image_utils import InvalidImageError, prepare_jpeg

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


@app.get("/health")
async def health():
    return {"status": "ok", "mode": config.CLASSIFIER_MODE}


@app.post("/classify", dependencies=[Depends(require_token)])
async def classify_image(request: Request, image: UploadFile | None = File(None)):
    # Terima multipart (field `image`) atau raw body (Content-Type: image/jpeg)
    raw = await image.read() if image is not None else await request.body()
    if not raw:
        raise HTTPException(status_code=400, detail="Gambar kosong")
    if len(raw) > config.MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Gambar terlalu besar")

    try:
        jpeg = prepare_jpeg(raw)
    except InvalidImageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        result = await classify(request.app.state.http, jpeg)
    except ClassifierError as exc:
        log.error("Klasifikasi gagal: %s", exc)
        raise HTTPException(status_code=502, detail="Gagal mengklasifikasi gambar") from exc

    log.info("Hasil: %s (source=%s, confidence=%s)", result.category, result.source, result.confidence)
    return {name: name == result.category for name in config.CATEGORIES}
