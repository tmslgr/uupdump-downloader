from __future__ import annotations

import os
import shutil
import subprocess
from typing import Optional


class ConverterNotFoundError(Exception):
    pass


def ensure_executable_on_path(name: str) -> bool:
    return shutil.which(name) is not None


def run_converter(
    converter_dir: str,
    uups_dir: str,
    *,
    compression: str = "wim",
    virtual_editions: bool = False,
) -> int:
    script_path = os.path.join(converter_dir, "convert.sh")
    if not os.path.isfile(script_path):
        raise ConverterNotFoundError(
            f"convert.sh not found in {converter_dir}. See https://git.uupdump.net/uup-dump/converter"
        )

    # Basic prerequisite hints (do not enforce)
    # aria2c, cabextract, wimlib-imagex, chntpw, genisoimage/mkisofs
    missing = []
    for tool in ("aria2c", "cabextract", "wimlib-imagex", "chntpw"):
        if not ensure_executable_on_path(tool):
            missing.append(tool)
    if not (ensure_executable_on_path("genisoimage") or ensure_executable_on_path("mkisofs")):
        missing.append("genisoimage/mkisofs")

    if missing:
        print(
            "Warning: missing tools: " + ", ".join(missing) + ". Conversion may fail until installed.",
            flush=True,
        )

    ve_flag = "1" if virtual_editions else "0"
    cmd = [script_path, compression, uups_dir, ve_flag]
    proc = subprocess.run(cmd)
    return proc.returncode


