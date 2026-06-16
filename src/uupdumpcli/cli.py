from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any
import re

from . import __version__
from .api import (
    DEFAULT_BASE_URL,
    DEFAULT_WEB_URL,
    UUPDumpApiError,
    filter_update_files,
    get_downloads,
    list_builds,
    list_editions,
    list_languages,
)
from .downloader import download_many
from .converter_integration import run_converter, ConverterNotFoundError


def _print_json(data: Any) -> None:
    print(json.dumps(data, indent=2, sort_keys=True))


def cmd_list(args: argparse.Namespace) -> int:
    builds = list_builds(search=args.search, sort_by_date=args.sort_by_date, base_url=args.base_url)
    if args.json:
        _print_json(builds)
        return 0
    for b in builds:
        title = b.get("title")
        build = b.get("build")
        arch = b.get("arch")
        uuid = b.get("uuid")
        created = b.get("created")
        print(f"{uuid}  {title}  build={build} arch={arch} created={created}")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    data = {}
    if args.langs:
        data["languages"] = list_languages(args.update_id, base_url=args.base_url)
    if args.editions:
        if not args.lang:
            print("--lang is required when using --editions", file=sys.stderr)
            return 2
        data["editions"] = list_editions(args.update_id, args.lang, base_url=args.base_url)
    if args.links:
        meta, files = get_downloads(args.update_id, args.lang, args.edition, base_url=args.base_url)
        if args.updates_only:
            keep = filter_update_files(args.update_id, list(files.keys()), web_url=args.web_url)
            files = {name: info for name, info in files.items() if name in keep}
        data["meta"] = meta
        data["files"] = files
    if not data:
        meta, files = get_downloads(args.update_id, base_url=args.base_url)
        names = list(files.keys())
        if args.updates_only:
            names = filter_update_files(args.update_id, names, web_url=args.web_url)
        data = {"meta": meta, "files": names}
    if args.json:
        _print_json(data)
    else:
        if "meta" in data:
            meta = data["meta"]
            print(f"updateName={meta.get('updateName')} build={meta.get('build')} arch={meta.get('arch')}")
        if "languages" in data:
            print("Languages:")
            for code, name in data["languages"].items():
                print(f"  {code}: {name}")
        if "editions" in data:
            print("Editions:")
            for e in data["editions"]:
                print(f"  {e}")
        if args.links and "files" in data:
            print("Files:")
            for filename, info in data["files"].items():
                size = info.get("size")
                print(f"  {filename}  size={size}")
    return 0


def cmd_download(args: argparse.Namespace) -> int:
    meta, files = get_downloads(args.update_id, args.lang, args.edition, base_url=args.base_url)
    if args.updates_only:
        keep = filter_update_files(args.update_id, list(files.keys()), web_url=args.web_url)
        files = {name: info for name, info in files.items() if name in keep}
    # Optional filtering for testing
    if args.include_regex:
        pattern = re.compile(args.include_regex)
        files = {name: info for name, info in files.items() if pattern.search(name)}
    if args.limit is not None:
        def _size(v: dict) -> int:
            try:
                return int(v.get("size") or 0)
            except Exception:
                return 0
        names = sorted(files.keys(), key=lambda n: _size(files[n]))[: max(0, int(args.limit))]
        files = {name: files[name] for name in names}
    print(f"Downloading update '{meta.get('updateName')}' build={meta.get('build')} arch={meta.get('arch')}")
    download_many(files, args.out, concurrency=args.concurrency, resume=not args.no_resume)
    print("Done.")
    if args.convert:
        conv_dir = args.convert_dir or os.environ.get("UUP_CONVERTER_DIR", "./converter")
        print(f"Running converter from {conv_dir} on {args.out} ...")
        try:
            rc = run_converter(conv_dir, args.out, compression=args.compress, virtual_editions=args.virtual_editions)
        except ConverterNotFoundError as e:
            print(str(e), file=sys.stderr)
            return 3
        if rc != 0:
            print(f"Converter failed with exit code {rc}", file=sys.stderr)
            return rc
        print("Converter finished.")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    _, files = get_downloads(args.update_id, args.lang, args.edition, base_url=args.base_url)
    errors = 0
    for filename, info in files.items():
        sha1 = str(info.get("sha1") or "").lower()
        path = os.path.join(args.path, filename)
        if not os.path.exists(path):
            print(f"MISSING {filename}")
            errors += 1
            continue
        import hashlib

        h = hashlib.sha1()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        actual = h.hexdigest().lower()
        if actual != sha1 and sha1:
            print(f"BADSUM {filename} expected={sha1} actual={actual}")
            errors += 1
        else:
            print(f"OK     {filename}")
    return 0 if errors == 0 else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="uupdump", description="UUP dump JSON API CLI")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Override JSON API base URL")
    parser.add_argument("--web-url", default=DEFAULT_WEB_URL, help="Override uupdump web base URL (used for --updates-only)")

    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="List known builds")
    p_list.add_argument("--search", default=None, help="Search string for builds")
    p_list.add_argument("--sort-by-date", action="store_true", help="Sort builds by date")
    p_list.add_argument("--json", action="store_true", help="Output JSON")
    p_list.set_defaults(func=cmd_list)

    p_show = sub.add_parser("show", help="Show details for an update ID")
    p_show.add_argument("update_id")
    p_show.add_argument("--lang", help="Language code (xx-xx)")
    p_show.add_argument("--edition", help="Edition name")
    p_show.add_argument("--langs", action="store_true", help="List available languages")
    p_show.add_argument("--editions", action="store_true", help="List editions for --lang")
    p_show.add_argument("--links", action="store_true", help="Show file links and metadata")
    p_show.add_argument("--updates-only", action="store_true", help="Only show cumulative update / SSU cabs (like findfiles.php?q=!updates)")
    p_show.add_argument("--json", action="store_true", help="Output JSON")
    p_show.set_defaults(func=cmd_show)

    p_dl = sub.add_parser("download", help="Download files for an update ID")
    p_dl.add_argument("update_id")
    p_dl.add_argument("--lang", required=False, help="Language code (xx-xx)")
    p_dl.add_argument("--edition", required=False, help="Edition name")
    p_dl.add_argument("--out", default="./uup-downloads", help="Destination directory")
    p_dl.add_argument("--concurrency", type=int, default=4, help="Parallel downloads")
    p_dl.add_argument("--no-resume", action="store_true", help="Disable resuming partial downloads")
    p_dl.add_argument("--updates-only", action="store_true", help="Only download cumulative update / SSU cabs (like findfiles.php?q=!updates)")
    p_dl.add_argument("--include-regex", help="Only download files whose names match this regex")
    p_dl.add_argument("--limit", type=int, help="Limit number of files to download (smallest by size first)")
    # Converter integration
    p_dl.add_argument("--convert", action="store_true", help="Run uup-dump/converter convert.sh after download")
    p_dl.add_argument("--convert-dir", help="Path to uup-dump/converter directory containing convert.sh")
    p_dl.add_argument("--compress", choices=["wim", "esd"], default="wim", help="Compression mode for converter")
    p_dl.add_argument("--virtual-editions", action="store_true", help="Enable virtual editions in converter")
    p_dl.set_defaults(func=cmd_download)

    p_verify = sub.add_parser("verify", help="Verify checksums for downloaded files")
    p_verify.add_argument("update_id")
    p_verify.add_argument("--lang", required=False)
    p_verify.add_argument("--edition", required=False)
    p_verify.add_argument("--path", required=True, help="Path to downloaded files")
    p_verify.set_defaults(func=cmd_verify)

    p_ver = sub.add_parser("version", help="Show version")
    p_ver.set_defaults(func=lambda args: (print(__version__), 0)[1])

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args) or 0)
    except UUPDumpApiError as e:
        print(f"API error: {e}", file=sys.stderr)
        return 2
    except BrokenPipeError:
        try:
            sys.stdout.close()
        finally:
            return 0
    except KeyboardInterrupt:
        print("Interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())


