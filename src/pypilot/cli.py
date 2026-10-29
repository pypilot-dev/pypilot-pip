"""
pypilot.cli: the `pypilot` command.

Every argument is passed to the native engine unchanged (including
`pypilot completions <shell>`), except a lone `--version` / `-V`, which the
wrapper answers itself so it can also report its own version and any skew
between the wrapper and the engine it found.
"""

from __future__ import annotations

import subprocess
import sys
from typing import List, Optional, Sequence

from . import __version__
from .binary import BUNDLED_VERSION, DEFAULT_TAG
from .engine import (
    SOURCE_CARGO,
    SOURCE_OVERRIDE,
    SOURCE_PATH,
    EngineInfo,
    Version,
    ensure_binary,
    locate_engine,
    parse_version,
)

_VERSION_FLAGS = (["--version"], ["-V"])


def _fmt(version: Version) -> str:
    return ".".join(map(str, version))


def skew_warnings(info: EngineInfo, version: Optional[Version]) -> List[str]:
    """Why the engine in use may not be the one this package was released with."""
    if info.source == SOURCE_OVERRIDE:
        return []
    if version is None:
        return [f"could not read a version from the engine at {info.path}"]
    where = {SOURCE_CARGO: "~/.cargo/bin", SOURCE_PATH: "PATH"}.get(info.source)
    warnings: List[str] = []
    if version < BUNDLED_VERSION:
        warnings.append(
            f"engine {_fmt(version)} is older than {DEFAULT_TAG}, the release "
            f"pypilot-cli {__version__} pins; newer commands may be missing"
        )
    if where is not None and version != BUNDLED_VERSION:
        warnings.append(
            f"using the engine from {where} ({info.path}) instead of the pinned "
            f"{DEFAULT_TAG}; update or remove it to use the pinned engine"
        )
    return warnings


def print_version() -> int:
    """`pypilot --version`.

    stdout carries only the engine's own `pypilot X.Y.Z` line, because editor
    extensions run `pypilot --version` and parse exactly that. The wrapper's
    version and any warnings go to stderr.
    """
    try:
        info = locate_engine()
    except Exception as e:
        print(f"pypilot-cli {__version__}", file=sys.stderr)
        print(f"Error: failed to locate or download PyPilot native engine: {e}", file=sys.stderr)
        return 1
    try:
        res = subprocess.run(
            [str(info.path), "--version"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        print(f"pypilot-cli {__version__}", file=sys.stderr)
        print(f"Error: could not run the engine at {info.path}: {e}", file=sys.stderr)
        return 1

    line = res.stdout.strip()
    if res.returncode != 0 or not line:
        sys.stderr.write(res.stderr)
        print(f"pypilot-cli {__version__}", file=sys.stderr)
        print(f"Error: `{info.path} --version` failed", file=sys.stderr)
        return res.returncode or 1

    print(line, flush=True)
    print(f"pypilot-cli {__version__} (engine: {info.source}, {info.path})", file=sys.stderr)
    for warning in skew_warnings(info, parse_version(line)):
        print(f"warning: {warning}", file=sys.stderr)
    return 0


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = list(sys.argv[1:] if argv is None else argv)
    if args in _VERSION_FLAGS:
        sys.exit(print_version())

    try:
        bin_path = ensure_binary()
    except Exception as e:
        print(f"Error: failed to locate or download PyPilot native engine: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        proc = subprocess.run([str(bin_path), *args])
        sys.exit(proc.returncode)
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    main()
