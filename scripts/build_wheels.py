"""
Build every pypilot-cli distribution into `dist/`:

- the sdist and the pure-Python wheel (they download the engine on first use,
  for platforms without a platform wheel), and
- one platform wheel per engine release asset, bundling the engine of
  `DEFAULT_TAG` after checking it against `ENGINE_SHA256`.

    uv run python scripts/build_wheels.py                     # everything
    uv run python scripts/build_wheels.py --only pypilot-windows-x64.zip --no-pure --no-sdist

Wheels holding a Linux or macOS engine must be built on Linux or macOS: the
wheel records each file's mode from disk, and Windows has no executable bit.
"""

from __future__ import annotations

import argparse
import importlib.machinery
import importlib.util
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from types import ModuleType
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from pypilot import binary, engine  # noqa: E402


def _load_hook() -> ModuleType:
    loader = importlib.machinery.SourceFileLoader("hatch_build", str(ROOT / "hatch_build.py"))
    spec = importlib.util.spec_from_loader("hatch_build", loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def _uv_build(kind: str, out: Path, env: Dict[str, str]) -> None:
    uv = shutil.which("uv")
    if uv is None:
        sys.exit("uv is required: https://docs.astral.sh/uv/")
    subprocess.run([uv, "build", f"--{kind}", "--out-dir", str(out), str(ROOT)], env=env, check=True)


def _only_new(out: Path, before: List[Path], pattern: str) -> Path:
    built = [p for p in out.glob(pattern) if p not in before]
    if len(built) != 1:
        sys.exit(f"expected one new {pattern} in {out}, found {built}")
    return built[0]


def _stage_engine(asset: str, name: str) -> Path:
    """Download and verify `asset` of the pinned release; extract its binary."""
    stage = ROOT / "build" / "engine" / asset
    shutil.rmtree(stage, ignore_errors=True)
    stage.mkdir(parents=True)
    with tempfile.TemporaryDirectory() as tmp:
        archive = engine.download_verified_archive(binary.DEFAULT_TAG, asset, tmp)
        engine.extract_archive(archive, stage)
    exe = stage / name
    if not exe.is_file():
        sys.exit(f"{name} not found in {asset}")
    if not name.endswith(".exe"):
        exe.chmod(0o755)
    return stage


def _check_platform_wheel(wheel: Path, name: str, staged: Path) -> None:
    member = f"pypilot/_engine/{name}"
    with zipfile.ZipFile(wheel) as zf:
        info = zf.getinfo(member)
        if zf.read(member) != staged.read_bytes():
            sys.exit(f"{wheel.name}: {member} differs from the verified engine")
        if not name.endswith(".exe") and not (info.external_attr >> 16) & stat.S_IXUSR:
            sys.exit(f"{wheel.name}: {member} is not executable")
        if "Root-Is-Purelib: false" not in zf.read(next(n for n in zf.namelist() if n.endswith("/WHEEL"))).decode():
            sys.exit(f"{wheel.name}: not marked as a platform wheel")


def main(argv: Optional[List[str]] = None) -> None:
    hook = _load_hook()
    platforms: Dict[str, Tuple[str, str]] = hook.WHEEL_PLATFORMS
    if set(platforms) != set(binary.ENGINE_SHA256):
        sys.exit("hatch_build.WHEEL_PLATFORMS and binary.ENGINE_SHA256 list different assets")

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=ROOT / "dist")
    parser.add_argument("--only", action="append", choices=sorted(platforms), help="platform wheel(s) to build")
    parser.add_argument("--no-pure", action="store_true", help="skip the pure-Python wheel")
    parser.add_argument("--no-sdist", action="store_true", help="skip the sdist")
    args = parser.parse_args(argv)

    out: Path = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    base_env = {k: v for k, v in os.environ.items() if k not in ("PYPILOT_ENGINE_ASSET", "PYPILOT_ENGINE_DIR")}
    # The bundled engine must be the pinned one, whatever the shell says.
    base_env.pop(engine.ENV_ENGINE_VERSION, None)
    base_env.pop(engine.ENV_OFFLINE, None)
    os.environ.pop(engine.ENV_ENGINE_VERSION, None)

    if not args.no_sdist:
        before = list(out.glob("*.tar.gz"))
        _uv_build("sdist", out, base_env)
        print(f"built {_only_new(out, before, '*.tar.gz').name}")

    if not args.no_pure:
        before = list(out.glob("*-py3-none-any.whl"))
        _uv_build("wheel", out, base_env)
        wheel = _only_new(out, before, "*-py3-none-any.whl")
        with zipfile.ZipFile(wheel) as zf:
            if any("/_engine/" in n for n in zf.namelist()):
                sys.exit(f"{wheel.name}: the pure wheel must not bundle an engine")
        print(f"built {wheel.name}")

    for asset in args.only or sorted(platforms):
        tag, name = platforms[asset]
        if sys.platform == "win32" and not name.endswith(".exe"):
            sys.exit(f"{asset}: build this wheel on Linux or macOS so the engine keeps its executable bit")
        stage = _stage_engine(asset, name)
        pattern = f"*-py3-none-{tag}.whl"
        before = list(out.glob(pattern))
        env = dict(base_env, PYPILOT_ENGINE_ASSET=asset, PYPILOT_ENGINE_DIR=str(stage))
        _uv_build("wheel", out, env)
        wheel = _only_new(out, before, pattern)
        _check_platform_wheel(wheel, name, stage / name)
        print(f"built {wheel.name} with the {binary.DEFAULT_TAG} engine")


if __name__ == "__main__":
    main()
