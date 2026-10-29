"""
pypilot.cli — Command-line interface entry point.
"""

from __future__ import annotations

import subprocess
import sys
from .engine import ensure_binary


def main() -> None:
    try:
        bin_path = ensure_binary()
    except Exception as e:
        print(f"Error: failed to locate or download PyPilot native engine: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        proc = subprocess.run([str(bin_path), *sys.argv[1:]])
        sys.exit(proc.returncode)
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    main()
