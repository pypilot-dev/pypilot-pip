"""
Hatch build hook: turn the pure wheel into a platform wheel bundling the engine.

Without `PYPILOT_ENGINE_ASSET` this does nothing, so `uv build` still makes the
pure-Python wheel (which downloads the engine on first use) and the sdist.

With `PYPILOT_ENGINE_ASSET=<release asset name>`, the engine binary already
extracted (and verified) by `scripts/build_wheels.py` into
`PYPILOT_ENGINE_DIR` (default `build/engine/<asset>/`) is packed as
`pypilot/_engine/pypilot[.exe]` and the wheel gets that platform's tag.

Wheel platform tags, from the v1.2.2 binaries themselves:

- linux-x64: the ELF needs GLIBC_2.34 (`__libc_start_main@GLIBC_2.34`, the
  pthread symbols); its GLIBC_2.39 need (`pidfd_spawnp`, `pidfd_getpid`) is
  marked WEAK, which ld.so does not enforce. So manylinux_2_34, not 2_17.
- darwin-arm64: LC_BUILD_VERSION minos 11.0.
- darwin-x64: LC_VERSION_MIN_MACOSX 10.12.
- windows-x64: PE32+ x86-64.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Tuple

from hatchling.builders.hooks.plugin.interface import BuildHookInterface

# Release asset -> (wheel platform tag, binary name inside the archive).
WHEEL_PLATFORMS: Dict[str, Tuple[str, str]] = {
    "pypilot-linux-x64.tar.gz": ("manylinux_2_34_x86_64", "pypilot"),
    "pypilot-darwin-arm64.tar.gz": ("macosx_11_0_arm64", "pypilot"),
    "pypilot-darwin-x64.tar.gz": ("macosx_10_12_x86_64", "pypilot"),
    "pypilot-windows-x64.zip": ("win_amd64", "pypilot.exe"),
}


class EngineWheelHook(BuildHookInterface):
    PLUGIN_NAME = "custom"

    def initialize(self, version: str, build_data: Dict[str, Any]) -> None:
        asset = os.environ.get("PYPILOT_ENGINE_ASSET", "").strip()
        if self.target_name != "wheel" or version == "editable" or not asset:
            return
        if asset not in WHEEL_PLATFORMS:
            raise ValueError(f"PYPILOT_ENGINE_ASSET={asset!r} is not one of {sorted(WHEEL_PLATFORMS)}")
        platform_tag, name = WHEEL_PLATFORMS[asset]
        engine_dir = Path(os.environ.get("PYPILOT_ENGINE_DIR") or Path(self.root, "build", "engine", asset))
        binary = engine_dir / name
        if not binary.is_file():
            raise FileNotFoundError(f"{binary} is missing; build platform wheels with scripts/build_wheels.py")

        build_data["pure_python"] = False
        build_data["tag"] = f"py3-none-{platform_tag}"
        build_data["force_include"][str(binary)] = f"pypilot/_engine/{name}"
