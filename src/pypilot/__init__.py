"""
PyPilot — Deterministic Python environment doctor and dependency manager.
"""

from __future__ import annotations

__version__ = "1.2.2"

from .api import RunResult, arun, run  # noqa: E402
from .engine import (  # noqa: E402
    EngineDownloadError,
    EngineError,
    EngineInfo,
    EngineNotFoundError,
    EngineVerificationError,
    ensure_binary,
    get_cache_dir,
    locate_engine,
)

__all__ = [
    "EngineDownloadError",
    "EngineError",
    "EngineInfo",
    "EngineNotFoundError",
    "EngineVerificationError",
    "RunResult",
    "__version__",
    "arun",
    "ensure_binary",
    "get_cache_dir",
    "locate_engine",
    "run",
]
