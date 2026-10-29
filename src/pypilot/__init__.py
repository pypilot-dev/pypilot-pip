"""
PyPilot — Deterministic Python environment doctor and dependency manager.
"""

from __future__ import annotations

import subprocess
import sys
from typing import List, Optional

from .engine import ensure_binary, get_cache_dir

__version__ = "1.2.2"


def run(args: Optional[List[str]] = None, capture_output: bool = False) -> subprocess.CompletedProcess[str]:
    """
    Run PyPilot programmatically.

    Example:
        import pypilot
        res = pypilot.run(["doctor"])
        print(res.stdout)
    """
    bin_path = ensure_binary()
    cmd = [str(bin_path)]
    if args:
        cmd.extend(args)
    return subprocess.run(cmd, capture_output=capture_output, text=True, check=False)


__all__ = ["ensure_binary", "get_cache_dir", "run", "__version__"]
