"""The pictures of rich broadcasts, for Telegram to download. No auth: the
names are unguessable, and a picture never changes under its name."""
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.services import broadcast_media

router = APIRouter(prefix="/broadcasts", tags=["broadcasts"])


@router.get("/media/{name}")
def broadcast_media_file(name: str):
    path = broadcast_media.path_of(name)
    if not path:
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(
        path,
        media_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )
