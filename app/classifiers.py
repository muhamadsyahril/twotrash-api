import base64
import json
import logging
import re
import uuid
from dataclasses import dataclass

import httpx

from app import config
from app.prompts import CRITERIA, QUESTION, SUMOPOD_SYSTEM_PROMPT

log = logging.getLogger("trash.classifier")


class ClassifierError(RuntimeError):
    pass


@dataclass
class Classification:
    category: str
    confidence: float | None
    source: str


async def classify_with_jev(client: httpx.AsyncClient, jpeg: bytes) -> Classification:
    if not config.TYPESAFE_API_KEY:
        raise ClassifierError("TYPESAFE_API_KEY belum diset")

    ref = f"img-{uuid.uuid4()}"
    body = {
        "model": config.TYPESAFE_MODEL,
        "state": {"photo": ref},
        "assets": {
            ref: {
                "type": "image",
                "format": "jpg",
                "data_base64": base64.b64encode(jpeg).decode("ascii"),
            }
        },
        "questions": {
            "waste": {"type": "choice", "instructions": QUESTION, "criteria": CRITERIA}
        },
    }
    try:
        resp = await client.post(
            f"{config.TYPESAFE_BASE_URL}/v1/systemone",
            headers={
                "Authorization": f"Bearer {config.TYPESAFE_API_KEY}",
                "TypeSafe-Danger-Zone-Images": "true",
            },
            json=body,
        )
    except httpx.HTTPError as exc:
        raise ClassifierError(f"Jev tidak bisa dihubungi: {exc}") from exc

    if resp.status_code != 200:
        raise ClassifierError(f"Jev HTTP {resp.status_code}: {resp.text[:300]}")

    answer = resp.json()["answers"]["waste"]
    category = answer.get("choice")
    if category not in config.CATEGORIES:
        raise ClassifierError(f"Jev mengembalikan kategori tidak dikenal: {category!r}")
    return Classification(category, answer.get("confidence"), "jev")


async def classify_with_sumopod(client: httpx.AsyncClient, jpeg: bytes) -> Classification:
    if not config.SUMOPOD_API_KEY:
        raise ClassifierError("SUMOPOD_API_KEY belum diset")

    data_url = "data:image/jpeg;base64," + base64.b64encode(jpeg).decode("ascii")
    body = {
        "model": config.SUMOPOD_MODEL,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": SUMOPOD_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Classify the waste in this photo."},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            },
        ],
    }
    try:
        resp = await client.post(
            f"{config.SUMOPOD_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {config.SUMOPOD_API_KEY}"},
            json=body,
        )
    except httpx.HTTPError as exc:
        raise ClassifierError(f"Sumopod tidak bisa dihubungi: {exc}") from exc

    if resp.status_code != 200:
        raise ClassifierError(f"Sumopod HTTP {resp.status_code}: {resp.text[:300]}")

    content = resp.json()["choices"][0]["message"]["content"] or ""
    return Classification(_parse_category(content), None, "sumopod")


def _parse_category(text: str) -> str:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            value = str(json.loads(match.group(0)).get("category", "")).lower()
            if value in config.CATEGORIES:
                return value
        except json.JSONDecodeError:
            pass
    # "anorganic" mengandung "organic", jadi cek dulu yang lebih spesifik
    lowered = text.lower()
    for name in ("anorganic", "inorganic", "organic", "other"):
        if name in lowered:
            return "anorganic" if name == "inorganic" else name
    raise ClassifierError(f"Jawaban Sumopod tidak bisa dibaca: {text[:200]!r}")


async def classify(client: httpx.AsyncClient, jpeg: bytes) -> Classification:
    mode = config.CLASSIFIER_MODE
    if mode == "jev":
        return await classify_with_jev(client, jpeg)
    if mode == "sumopod":
        return await classify_with_sumopod(client, jpeg)

    try:
        result = await classify_with_jev(client, jpeg)
    except ClassifierError as exc:
        log.warning("Jev gagal, fallback ke Sumopod: %s", exc)
        return await classify_with_sumopod(client, jpeg)

    if result.confidence is not None and result.confidence < config.JEV_MIN_CONFIDENCE:
        log.info("Confidence Jev %.2f rendah, cek ulang ke Sumopod", result.confidence)
        try:
            return await classify_with_sumopod(client, jpeg)
        except ClassifierError as exc:
            log.warning("Sumopod gagal, pakai hasil Jev: %s", exc)
    return result
