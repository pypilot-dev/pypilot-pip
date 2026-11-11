"""
pypilot.binary: the engine pin, plus the names this module used to define.

`DEFAULT_TAG` and `ENGINE_SHA256` are a contract with the release-coordination
workflow, which bumps exactly these two assignments in this file when a new
engine ships. Keep them literal, one asset per line, so a plain text edit can
update them.

The locate/download code moved to `pypilot.engine`; the old names stay
importable from here (`from pypilot.binary import ensure_binary` still works).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, Tuple

GITHUB_REPO = "pypilot-dev/pypilot"

# The engine release this package is pinned to.
DEFAULT_TAG = "v1.4.1"

# SHA-256 of every release asset of DEFAULT_TAG. A download is checked against
# this before it is extracted or run.
ENGINE_SHA256: Dict[str, str] = {
    "pypilot-darwin-arm64.tar.gz": "bf15ab7eb6a906c04920d449c3e532767c8b0e3a4f78fc2f6e40610cce17a207",
    "pypilot-darwin-x64.tar.gz": "58fa4d81e7a17e14912c0a295b2572c74a26e578330e06b9efb2dd2f85c1ddc3",
    "pypilot-linux-x64.tar.gz": "a4584ceec332eeed4ff1fe2f5917906e944369a98038c7fc9dd8607a2f553d49",
    "pypilot-windows-x64.zip": "b8e734df0dce85e7898a375054e4a73d3ca803624d205e17017eff3c040aeaec",
}

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
    "ENGINE_SHA256",
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
