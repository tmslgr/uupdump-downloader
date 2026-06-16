from __future__ import annotations

import os
import time
from html.parser import HTMLParser
from typing import Dict, List, Mapping, Optional, Set, Tuple
from urllib.parse import parse_qs, urlparse

import requests


DEFAULT_BASE_URL = os.environ.get(
    "UUPDUMP_JSON_API_BASE_URL", "https://api.uupdump.net"
)
DEFAULT_WEB_URL = os.environ.get(
    "UUPDUMP_WEB_BASE_URL", "https://uupdump.net"
)


class UUPDumpApiError(Exception):
    pass


class _FileLinkParser(HTMLParser):
    """Extracts filenames from the file= query param in links on findfiles.php."""

    def __init__(self) -> None:
        super().__init__()
        self.filenames: List[str] = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag != "a":
            return
        for name, value in attrs:
            if name == "href" and value:
                qs = parse_qs(urlparse(value).query)
                if "file" in qs:
                    self.filenames.extend(qs["file"])


def get_update_filenames(update_id: str, *, web_url: str = DEFAULT_WEB_URL) -> Set[str]:
    """Return the set of filenames listed by the server-side !updates filter."""
    url = f"{web_url.rstrip('/')}/findfiles.php"
    resp = requests.get(url, params={"id": update_id, "q": "!updates"}, timeout=60)
    resp.raise_for_status()
    parser = _FileLinkParser()
    parser.feed(resp.text)
    return set(parser.filenames)


def filter_update_files(update_id: str, names: List[str], *, web_url: str = DEFAULT_WEB_URL) -> List[str]:
    allowed = get_update_filenames(update_id, web_url=web_url)
    return [name for name in names if name in allowed]


def _raise_for_api_error(payload: Mapping) -> None:
    response = payload.get("response")
    if isinstance(response, Mapping) and "error" in response:
        err = response.get("error")
        raise UUPDumpApiError(str(err))


def _get_json(
    path: str,
    params: Optional[Mapping[str, str]] = None,
    *,
    base_url: str = DEFAULT_BASE_URL,
    max_retries: int = 5,
    base_delay_sec: float = 1.0,
) -> Mapping:
    url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
    headers = {"User-Agent": f"uupdumpcli/{__import__('uupdumpcli').__version__}"}
    last_exc: Optional[Exception] = None
    for attempt in range(max(1, max_retries)):
        try:
            resp = requests.get(url, params=params, timeout=60, headers=headers)
            if resp.status_code in (429, 503):
                # Respect Retry-After if present
                retry_after = resp.headers.get("Retry-After")
                try:
                    delay = float(retry_after) if retry_after else base_delay_sec * (2 ** attempt)
                except Exception:
                    delay = base_delay_sec * (2 ** attempt)
                time.sleep(min(delay, 30))
                last_exc = requests.HTTPError(f"{resp.status_code} Too Many Requests")
                continue
            resp.raise_for_status()
            data = resp.json()
            _raise_for_api_error(data)
            return data
        except requests.RequestException as e:
            last_exc = e
            time.sleep(base_delay_sec * (2 ** attempt))
        except ValueError as e:
            # JSON decode error; retry once
            last_exc = e
            time.sleep(base_delay_sec * (2 ** attempt))
    assert last_exc is not None
    raise last_exc


def list_builds(search: Optional[str] = None, sort_by_date: bool = True, *, base_url: str = DEFAULT_BASE_URL) -> List[Mapping]:
    params: Dict[str, str] = {}
    if search:
        params["search"] = search
    if sort_by_date:
        params["sortByDate"] = "1"
    data = _get_json("listid.php", params=params, base_url=base_url)
    response = data.get("response", {})
    builds = response.get("builds", [])
    # Some API responses may return a mapping keyed by UUID; normalize to list of dicts
    if isinstance(builds, dict):
        return list(builds.values())
    return list(builds)


def list_languages(update_id: str, *, base_url: str = DEFAULT_BASE_URL) -> Mapping[str, str]:
    data = _get_json("listlangs.php", params={"id": update_id}, base_url=base_url)
    return data.get("response", {}).get("langs", {})


def list_editions(update_id: str, lang: str, *, base_url: str = DEFAULT_BASE_URL) -> List[str]:
    data = _get_json(
        "listeditions.php", params={"id": update_id, "lang": lang}, base_url=base_url
    )
    return data.get("response", {}).get("editions", [])


def get_downloads(update_id: str, lang: Optional[str] = None, edition: Optional[str] = None, *, base_url: str = DEFAULT_BASE_URL) -> Tuple[Mapping, Mapping[str, Mapping]]:
    params: Dict[str, str] = {"id": update_id}
    if lang:
        params["lang"] = lang
    if edition:
        params["edition"] = edition
    data = _get_json("get.php", params=params, base_url=base_url)
    response = data.get("response", {})
    meta = {k: response.get(k) for k in ("updateName", "arch", "build")}
    files = response.get("files", {})
    return meta, files


