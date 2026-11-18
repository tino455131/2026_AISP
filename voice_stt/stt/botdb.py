"""Load discord_bot/transcript_store.py so voice_stt writes the bot's database.

The bot and voice_stt use different virtual environments (the speech packages
are large), but transcript_store.py only needs the standard library, so we
load that one file directly instead of installing the bot as a package.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = REPO_ROOT / "discord_bot" / "data" / "messages.sqlite3"


def load_transcript_store(repo_root: Path = REPO_ROOT) -> ModuleType:
    name = "transcript_store"
    if name in sys.modules:
        return sys.modules[name]
    path = repo_root / "discord_bot" / "transcript_store.py"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # dataclasses look their module up here
    spec.loader.exec_module(module)
    return module
