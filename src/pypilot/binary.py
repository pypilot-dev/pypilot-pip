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
DEFAULT_TAG = "v1.4.0"

# SHA-256 of every release asset of DEFAULT_TAG. A download is checked against
# this before it is extracted or run.
ENGINE_SHA256: Dict[str, str] = {
    "pypilot-darwin-arm64.tar.gz": "af36f0f30dd99ca0c1edaffa1f232e8227f129ff367aa2ccb385cb79a230f206",
    "pypilot-darwin-x64.tar.gz": "20ee556805efdcea2fe0a57dc717f2892eba6701f2e63198342ef3bf84048d8a",
    "pypilot-linux-x64.tar.gz": "1ea4ab9ab20e5177fee62b934ebdd052386804c346fc7157dec35f7729da036e",
    "pypilot-windows-x64.zip": "41ca6f506c7ddc408407c1d49e80c054e533812a685971994394822148be507d",
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
