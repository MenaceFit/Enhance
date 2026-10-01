"""Signed file delivery for the local storage backend (S3 serves presigned URLs directly)."""

from __future__ import annotations

import mimetypes

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from app.core.storage import LocalStorage, get_storage

router = APIRouter(tags=["files"], include_in_schema=False)


@router.get("/files/{key:path}")
def serve(key: str, exp: int = Query(...), sig: str = Query(...), dl: str = Query(default="")):
    st = get_storage()
    if not isinstance(st, LocalStorage):
        raise HTTPException(404)
    if not st.verify(key, exp, sig, dl):
        raise HTTPException(403, "Lien expiré ou invalide.")
    try:
        path = st.path_for(key)
    except ValueError as exc:
        raise HTTPException(404) from exc
    if not path.is_file():
        raise HTTPException(404)
    headers = {"Cache-Control": "private, max-age=3600", "X-Robots-Tag": "noindex, nofollow"}
    media = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    if dl:
        return FileResponse(path, media_type=media, filename=dl, headers=headers)
    return FileResponse(path, media_type=media, headers=headers)
