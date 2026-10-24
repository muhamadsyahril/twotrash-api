import io

from PIL import Image, ImageOps, UnidentifiedImageError

# Batas gambar TypeSafe: tiap sisi 280..1568 px, PNG/JPEG baseline
MIN_SIDE = 280
MAX_SIDE = 1568


class InvalidImageError(ValueError):
    pass


def prepare_jpeg(raw: bytes) -> bytes:
    try:
        with Image.open(io.BytesIO(raw)) as original:
            img = ImageOps.exif_transpose(original).convert("RGB")
    except (UnidentifiedImageError, OSError) as exc:
        raise InvalidImageError("File bukan gambar yang valid") from exc

    img.thumbnail((MAX_SIDE, MAX_SIDE))

    w, h = img.size
    if min(w, h) < MIN_SIDE:
        scale = MIN_SIDE / min(w, h)
        img = img.resize(
            (min(MAX_SIDE, round(w * scale)), min(MAX_SIDE, round(h * scale))),
            Image.LANCZOS,
        )

    out = io.BytesIO()
    img.save(out, "JPEG", quality=88)
    return out.getvalue()
