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
DEFAULT_TAG = "v1.3.0"

# SHA-256 of every release asset of DEFAULT_TAG. A download is checked against
# this before it is extracted or run.
ENGINE_SHA256: Dict[str, str] = {
    "pypilot-darwin-arm64.tar.gz": "7e8c76180d704b3f887a078e8225ee9c9b26720607234afe4cdaab637a8b8ba7",
    "pypilot-darwin-x64.tar.gz": "0ea5d56780500ba19edb94c992629bed5304d4bc53084434e98ed4747d6a4432",
    "pypilot-linux-x64.tar.gz": "9b225dd1015ce32f329413e455f593b6090eb0e6f6a2d85ef8edd597bf1afe32",
    "pypilot-windows-x64.zip": "aab0efddd8abf984696055a8608624c68309909e8aaddd21784a8dc4f3db5a58",
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
