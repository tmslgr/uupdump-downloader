from __future__ import annotations

import hashlib
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Mapping, Optional

import requests
from tqdm import tqdm


CHUNK_SIZE = 1024 * 1024


@dataclass
class DownloadItem:
    filename: str
    url: str
    sha1: Optional[str] = None
    size: Optional[int] = None


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def _calc_sha1(path: str) -> str:
    sha1 = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            sha1.update(chunk)
    return sha1.hexdigest()


def download_file(item: DownloadItem, dest_dir: str, *, resume: bool = True, session: Optional[requests.Session] = None, progress: Optional[tqdm] = None) -> str:
    _ensure_dir(dest_dir)
    target_path = os.path.join(dest_dir, item.filename)
    temp_path = target_path + ".part"

    sess = session or requests.Session()

    headers = {}
    mode = "wb"
    existing = 0
    if resume and os.path.exists(temp_path):
        existing = os.path.getsize(temp_path)
        if existing > 0:
            headers["Range"] = f"bytes={existing}-"
            mode = "ab"

    with sess.get(item.url, headers=headers, stream=True, timeout=120) as r:
        r.raise_for_status()
        total = None
        if "Content-Length" in r.headers:
            try:
                total = int(r.headers["Content-Length"]) + existing
            except Exception:
                total = None

        bar = progress or tqdm(total=total, unit="B", unit_scale=True, desc=item.filename, initial=existing)
        with open(temp_path, mode) as f:
            for chunk in r.iter_content(chunk_size=CHUNK_SIZE):
                if not chunk:
                    continue
                f.write(chunk)
                bar.update(len(chunk))
        if progress is None:
            bar.close()

    os.replace(temp_path, target_path)

    if item.sha1:
        actual = _calc_sha1(target_path)
        if actual.lower() != item.sha1.lower():
            raise ValueError(f"SHA1 mismatch for {item.filename}: expected {item.sha1}, got {actual}")

    return target_path


def download_many(files: Mapping[str, Mapping], dest_dir: str, *, concurrency: int = 4, resume: bool = True) -> None:
    _ensure_dir(dest_dir)

    items = []
    for filename, info in files.items():
        url = info.get("url")
        if not url:
            continue
        sha1 = info.get("sha1")
        size_raw = info.get("size")
        try:
            size = int(size_raw) if size_raw is not None else None
        except Exception:
            size = None
        items.append(DownloadItem(filename=filename, url=url, sha1=sha1, size=size))

    overall = tqdm(total=sum(i.size or 0 for i in items) or None, unit="B", unit_scale=True, desc="Total")

    lock = threading.Lock()

    def wrapped(item: DownloadItem) -> str:
        path = download_file(item, dest_dir, resume=resume)
        if item.size:
            with lock:
                overall.update(item.size)
        return path

    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        futures = [pool.submit(wrapped, i) for i in items]
        for fut in as_completed(futures):
            fut.result()

    overall.close()


