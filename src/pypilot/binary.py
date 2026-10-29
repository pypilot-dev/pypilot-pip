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
DEFAULT_TAG = "v1.2.2"

# SHA-256 of every release asset of DEFAULT_TAG. A download is checked against
# this before it is extracted or run.
ENGINE_SHA256: Dict[str, str] = {
    "pypilot-darwin-arm64.tar.gz": "02913af2d7864a86f422fe245c36d927dfc4962e2f6d6cc02d904b9e32309329",
    "pypilot-darwin-x64.tar.gz": "250bf3dfc2e0a2e5f796c9cba1ae41c4e89d2a8d8594429905cce692eb43d53f",
    "pypilot-linux-x64.tar.gz": "974c1523fce855697de4bef89ee6c9d8221d6368ebdd0e3b8e298e7d411e6ea3",
    "pypilot-windows-x64.zip": "e6f8471f55bd47c065353ab7a5239ef9e798b483525bf11bb6f742c05051877e",
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
