"""
pypilot.binary: the engine pin, plus the names this module used to define.

`DEFAULT_TAG` names the engine release this package ships.

The locate/download code moved to `pypilot.engine`; the old names stay
importable from here (`from pypilot.binary import ensure_binary` still works).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Tuple

GITHUB_REPO = "pypilot-dev/pypilot"

# The engine release this package is pinned to.
DEFAULT_TAG = "v1.2.2"

# Oldest helper accepted from ~/.cargo/bin or PATH.
MIN_VERSION: Tuple[int, int, int] = (1, 0, 2)

# The release this package ships with. A cached download older than this is
# replaced, so upgrading the pip package also upgrades the engine.
_major, _minor, _patch = (int(p) for p in DEFAULT_TAG.lstrip("v").split("."))
BUNDLED_VERSION: Tuple[int, int, int] = (_major, _minor, _patch)

_MOVED = (
    "binary_name",
    "download_binary",
    "ensure_binary",
    "extract_archive",
    "get_cache_dir",
    "get_platform_slug",
    "install_binary",
    "parse_version",
    "probe_binary",
)

if TYPE_CHECKING:
    from .engine import (
        binary_name,
        download_binary,
        ensure_binary,
        extract_archive,
        get_cache_dir,
        get_platform_slug,
        install_binary,
        parse_version,
        probe_binary,
    )


def __getattr__(name: str) -> Any:
    # Resolved lazily: `pypilot.engine` imports the pin from this module, so an
    # eager import here would be circular.
    if name in _MOVED:
        from . import engine

        return getattr(engine, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "BUNDLED_VERSION",
    "DEFAULT_TAG",
    "GITHUB_REPO",
    "MIN_VERSION",
    "binary_name",
    "download_binary",
    "ensure_binary",
    "extract_archive",
    "get_cache_dir",
    "get_platform_slug",
    "install_binary",
    "parse_version",
    "probe_binary",
]
