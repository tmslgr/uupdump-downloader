# uupdump-downloader

Forked from the project (https://github.com/phantomic12/uupdumpapi-downloader)[https://github.com/phantomic12/uupdumpapi-downloader]

Command-line utility to browse and download UUP files using the UUP dump JSON API.

# Install (editable)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

# Usage

- List builds:

```bash
uupdump list --search "Windows 11" --sort-by-date
```

- Show languages/editions for an update ID:

```bash
uupdump show 123e4567-e89b-12d3-a456-426614174000 --langs --editions --lang en-us
```

- Download files for an update ID:

```bash
uupdump download 123e4567-e89b-12d3-a456-426614174000 \
  --lang en-us --edition professional \
  --out ./downloads --concurrency 4 --no-resume
```

- Verify checksums only:

```bash
uupdump verify 123e4567-e89b-12d3-a456-426614174000 --lang en-us --edition professional --path ./downloads
```

