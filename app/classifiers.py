import base64
import json
import logging
import re
import uuid
from dataclasses import dataclass

import httpx

from app import config
from app.prompts import ITEM_CATEGORY, ITEM_CRITERIA, QUESTION, SUMOPOD_SYSTEM_PROMPT

log = logging.getLogger("trash.classifier")


class ClassifierError(RuntimeError):
    pass


@dataclass
class Classification:
    category: str
    item: str
    confidence: float | None
    source: str

    def as_response(self) -> dict:
        # Contoh: {"anorganic": true, "item": "kaleng_minuman"}
        return {self.category: True, "item": self.item}


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
            "item": {
                "type": "choice",
                "instructions": QUESTION,
                "criteria": ITEM_CRITERIA,
            }
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

    answer = resp.json()["answers"]["item"]
    item = answer.get("choice")
    if item not in ITEM_CATEGORY:
        raise ClassifierError(f"Jev mengembalikan item tidak dikenal: {item!r}")
    return Classification(ITEM_CATEGORY[item], item, answer.get("confidence"), "jev")


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
    item = _parse_item(content)
    return Classification(ITEM_CATEGORY[item], item, None, "sumopod")


def _parse_item(text: str) -> str:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            payload = json.loads(match.group(0))
            item = str(payload.get("item", "")).lower().strip()
            if item in ITEM_CATEGORY:
                return item
        except json.JSONDecodeError:
            pass

    lowered = text.lower().replace("-", "_").replace(" ", "_")
    # Label teks khusus
    if "kaleng_minuman" in lowered or "sampah_kaleng_minuman" in lowered:
        return "kaleng_minuman"

    # Cocokkan slug paling panjang dulu supaya "kulit_pisang" menang atas "kulit"
    for item in sorted(ITEM_CATEGORY, key=len, reverse=True):
        if item in lowered:
            return item

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
