"""Windows only: let CTranslate2 find the NVIDIA DLLs that pip installed.

`pip install nvidia-cublas-cu12 nvidia-cudnn-cu12` puts cuBLAS / cuDNN DLLs in
site-packages/nvidia/<name>/bin, which Windows does not search by default.
Call `add_nvidia_dll_dirs()` before the model is loaded.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def add_nvidia_dll_dirs() -> list[str]:
    if sys.platform != "win32":
        return []

    added: list[str] = []
    for entry in sys.path:
        nvidia_dir = Path(entry) / "nvidia"
        if not nvidia_dir.is_dir():
            continue
        for bin_dir in sorted(nvidia_dir.glob("*/bin")):
            path = str(bin_dir)
            if path in added:
                continue
            os.add_dll_directory(path)
            # Some DLLs are loaded with the plain PATH search, so add it there too.
            os.environ["PATH"] = path + os.pathsep + os.environ.get("PATH", "")
            added.append(path)
    return added
