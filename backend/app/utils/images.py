"""Shared image handling.

Both receipt uploads and broadcast covers need the same thing: proof that the
bytes really are an image, and a size cap. The client's content type is not
that proof — it is whatever the sender chose to claim.
"""
import io

from PIL import Image, ImageOps

MAX_DIM = 2000
JPEG_QUALITY = 85


def compress_image(raw: bytes, max_dim: int = MAX_DIM) -> tuple[bytes, str, str] | None:
    """Re-encode to a size-capped JPEG. Returns None when the bytes don't
    decode, which is the caller's cue that this was never an image."""
    try:
        img = Image.open(io.BytesIO(raw))
        img = ImageOps.exif_transpose(img)  # honour camera orientation
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        img.thumbnail((max_dim, max_dim))  # only shrinks; keeps aspect ratio
        out = io.BytesIO()
        img.save(out, format="JPEG", quality=JPEG_QUALITY, optimize=True)
        return out.getvalue(), ".jpg", "image/jpeg"
    except Exception:
        return None
