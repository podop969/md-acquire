from __future__ import annotations
import hashlib
import re
import zipfile
from pathlib import Path

from .http import Client
from .models import Candidate, WorkSpec

_ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED = {"CON", "PRN", "AUX", "NUL",
             *(f"COM{i}" for i in range(1, 10)),
             *(f"LPT{i}" for i in range(1, 10))}


def safe_name(value: str, maxlen: int = 120) -> str:
    name = _ILLEGAL.sub("_", value)
    name = re.sub(r"\s+", " ", name).strip(" .")
    if name.split(".")[0].upper() in _RESERVED:
        name = "_" + name
    return (name[:maxlen].strip(" .") or "untitled")


def filename_for(spec: WorkSpec, cand: Candidate) -> str:
    stem = safe_name(spec.title)
    if spec.authors:
        stem = f"{stem} - {safe_name(spec.authors[0], 40)}"
    return f"{stem}.{cand.fmt}"


def validate(path: Path, fmt: str) -> None:
    if fmt == "pdf":
        with open(path, "rb") as fh:
            if fh.read(5) != b"%PDF-":
                raise ValueError("file is not a PDF")
    elif fmt == "epub":
        try:
            with zipfile.ZipFile(path) as zf:
                if "mimetype" not in zf.namelist():
                    raise ValueError("EPUB missing mimetype entry")
                if zf.read("mimetype").strip() != b"application/epub+zip":
                    raise ValueError("EPUB has wrong mimetype")
        except zipfile.BadZipFile as exc:
            raise ValueError("not a zip/EPUB") from exc
    else:
        raise ValueError(f"unsupported format: {fmt}")


def looks_like_html(path: Path) -> bool:
    """Catch a truncated/failed download saved as bytes: HTML head means an error page."""
    try:
        with open(path, "rb") as fh:
            head = fh.read(256).lstrip()
    except OSError:
        return False
    return head[:1] == b"<" or b"<html" in head[:200].lower()


def download(client: Client, cand: Candidate, spec: WorkSpec, dest: Path) -> tuple[Path, str]:
    dest.mkdir(parents=True, exist_ok=True)
    final = dest / filename_for(spec, cand)
    if final.exists():
        digest = hashlib.sha256(final.read_bytes()).hexdigest()
        return final, digest

    r = client.get(cand.url, stream=True, allow_redirects=True)
    r.raise_for_status()
    ctype = (r.headers.get("content-type") or "").lower()
    if "text/html" in ctype:
        raise ValueError(f"server returned HTML, not {cand.fmt}")

    tmp = final.with_suffix(final.suffix + ".part")
    digest = hashlib.sha256()
    try:
        with open(tmp, "wb") as fh:
            for chunk in r.iter_content(64 * 1024):
                if chunk:
                    fh.write(chunk)
                    digest.update(chunk)
        if looks_like_html(tmp):
            raise ValueError("download body is HTML, not the document")
        validate(tmp, cand.fmt)
        tmp.replace(final)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
    return final, digest.hexdigest()