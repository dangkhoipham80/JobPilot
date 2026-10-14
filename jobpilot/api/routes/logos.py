"""Cached employer logos, served without the API token.

An ``<img>`` cannot send the ``X-API-Token`` header, so this one route is open —
the same choice the static dashboard files make. What it can serve is narrow:
only names matching ``logos.FILE_RE`` (a 20-hex content hash plus a raster
extension) from the logo directory. A name cannot be guessed from a company,
nothing lists the directory, and the files are company logos — pictures the
employers publish themselves.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from jobpilot.companies import logos as store

router = APIRouter(prefix="/logos", tags=["logos"])

_TYPES = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "gif": "image/gif",
    "webp": "image/webp",
    "ico": "image/x-icon",
}


@router.get("/{name}")
def logo(name: str) -> FileResponse:
    if not store.FILE_RE.match(name):
        raise HTTPException(status_code=404, detail="not found")
    path = store.logo_dir() / name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="not found")
    return FileResponse(
        path,
        media_type=_TYPES[name.rsplit(".", 1)[1]],
        # Named by content hash: the bytes behind a name never change.
        headers={
            "Cache-Control": "public, max-age=31536000, immutable",
            "X-Content-Type-Options": "nosniff",
        },
    )
