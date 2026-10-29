"""
pypilot.engine: locate or download the platform-matching native `pypilot` engine.
"""

from __future__ import annotations

import os
import platform
import shutil
import stat
import subprocess
import sys
import sysconfig
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from typing import Set

from .binary import BUNDLED_VERSION, DEFAULT_TAG, GITHUB_REPO, MIN_VERSION

# Set while probing a candidate engine. A `pypilot` on PATH can be this very
# wrapper (a console-script launcher), and probing it must not make it search
# PATH again.
_ENV_PROBING = "_PYPILOT_PROBING"


def get_platform_slug() -> tuple[str, str]:
    """
    Returns (slug, extension), e.g. ("windows-x64", "zip") or ("linux-x64", "tar.gz").
    """
    system = platform.system().lower()
    machine = platform.machine().lower()

    if system == "linux":
        if machine in ("x86_64", "amd64"):
            return "linux-x64", "tar.gz"
        raise RuntimeError(f"Unsupported Linux architecture for PyPilot: {machine}")
    elif system == "darwin":
        if machine in ("arm64", "aarch64"):
            return "darwin-arm64", "tar.gz"
        elif machine in ("x86_64", "amd64"):
            return "darwin-x64", "tar.gz"
        raise RuntimeError(f"Unsupported macOS architecture for PyPilot: {machine}")
    elif system == "windows":
        if machine in ("x86_64", "amd64"):
            return "windows-x64", "zip"
        raise RuntimeError(f"Unsupported Windows architecture for PyPilot: {machine}")
    else:
        raise RuntimeError(f"Unsupported operating system for PyPilot: {system}")


def get_cache_dir() -> Path:
    """Returns directory for storing cached PyPilot binaries."""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA")
        if base:
            cache = Path(base) / "pypilot" / "bin"
        else:
            cache = Path.home() / ".cache" / "pypilot" / "bin"
    else:
        base = os.environ.get("XDG_CACHE_HOME")
        if base:
            cache = Path(base) / "pypilot" / "bin"
        else:
            cache = Path.home() / ".cache" / "pypilot" / "bin"
    cache.mkdir(parents=True, exist_ok=True)
    return cache


def binary_name() -> str:
    return "pypilot.exe" if sys.platform == "win32" else "pypilot"


def parse_version(out: str) -> tuple[int, int, int] | None:
    # Example: "pypilot 1.0.2"
    for part in out.strip().split():
        components = part.split(".")
        if len(components) == 3 and all(c.isdigit() for c in components):
            return int(components[0]), int(components[1]), int(components[2])
    return None


def probe_binary(path: Path | str) -> tuple[int, int, int] | None:
    env = dict(os.environ)
    env[_ENV_PROBING] = "1"
    try:
        res = subprocess.run(
            [str(path), "--version"],
            capture_output=True,
            text=True,
            env=env,
            # macOS scans a freshly downloaded binary on its first launch, which
            # can take several seconds. Timing out here made a good engine look
            # broken and triggered a needless re-download.
            timeout=30,
            check=False,
        )
        if res.returncode == 0:
            return parse_version(res.stdout)
    except Exception:
        pass
    return None


def extract_archive(archive: Path | str, dest: Path | str) -> None:
    """Extract a downloaded `.zip` or `.tar.gz` release archive into `dest`."""
    if str(archive).endswith(".zip"):
        with zipfile.ZipFile(archive, "r") as zf:
            zf.extractall(dest)
        return
    with tarfile.open(archive, "r:gz") as tf:
        # Python 3.14 filters tar members by default and 3.12/3.13 warn that it
        # is coming. Ask for the same behaviour everywhere it is available (it
        # was backported to the late 3.8-3.11 releases): plain files only, and
        # nothing may land outside `dest`.
        if hasattr(tarfile, "data_filter"):
            tf.extractall(dest, filter="data")
        else:
            tf.extractall(dest)


def download_binary(tag: str = DEFAULT_TAG) -> Path:
    """Download prebuilt native binary from GitHub releases."""
    slug, ext = get_platform_slug()
    bin_name = binary_name()
    archive_name = f"pypilot-{slug}.{ext}"
    url = f"https://github.com/{GITHUB_REPO}/releases/download/{tag}/{archive_name}"

    cache_dir = get_cache_dir()
    dest_binary = cache_dir / bin_name

    print(f"PyPilot: downloading native engine from {url} ...", file=sys.stderr)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_archive = Path(tmpdir) / archive_name
        req = urllib.request.Request(url, headers={"User-Agent": "pypilot-python"})
        with urllib.request.urlopen(req) as resp, open(tmp_archive, "wb") as f:
            shutil.copyfileobj(resp, f)

        extract_archive(tmp_archive, tmpdir)

        extracted_bin = Path(tmpdir) / bin_name
        if not extracted_bin.exists():
            # Search subdirectories if any
            candidates = list(Path(tmpdir).rglob(bin_name))
            if candidates:
                extracted_bin = candidates[0]
            else:
                raise FileNotFoundError(f"{bin_name} not found in downloaded archive {archive_name}")

        install_binary(extracted_bin, dest_binary)

    return dest_binary


def install_binary(src: Path, dest: Path) -> None:
    """Put `src` at `dest` as a new file, never by rewriting `dest` in place.

    macOS caches what it knows about an executable per file. Overwriting a
    binary that was just run leaves the old cache entry pointing at new bytes,
    and the next launch fails with "Exec format error". Copying to a temporary
    name and renaming over `dest` gives it a fresh file instead.

    Windows has no such cache, but its antivirus briefly holds a freshly
    written .exe open, which makes an immediate rename fail with "Access is
    denied". There, a plain copy is both sufficient and reliable.
    """
    if sys.platform == "win32":
        shutil.copy2(src, dest)
        return

    tmp = dest.with_name(f".{dest.name}.{os.getpid()}.tmp")
    try:
        shutil.copy2(src, tmp)
        tmp.chmod(tmp.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        os.replace(tmp, dest)
    finally:
        if tmp.exists():
            tmp.unlink()


def _own_launchers() -> Set[str]:
    """Paths under which this wrapper itself may appear on PATH."""
    found: Set[str] = set()
    candidates = []
    try:
        candidates.append(Path(sysconfig.get_path("scripts")) / binary_name())
    except (KeyError, TypeError):
        pass
    if sys.argv and sys.argv[0]:
        candidates += [Path(sys.argv[0]), Path(sys.argv[0] + ".exe")]
    for candidate in candidates:
        try:
            found.add(os.path.normcase(str(candidate.resolve())))
        except OSError:
            pass
    return found


def ensure_binary() -> Path:
    """
    Locates an existing binary on PATH or in cache, or downloads it from GitHub.
    """
    bin_name = binary_name()

    # 1. Check if native binary is already in cache
    cached = get_cache_dir() / bin_name
    if cached.is_file():
        ver = probe_binary(cached)
        if ver and ver >= BUNDLED_VERSION:
            return cached

    # 2. Check ~/.cargo/bin
    cargo_bin = Path.home() / ".cargo" / "bin" / bin_name
    if cargo_bin.is_file():
        ver = probe_binary(cargo_bin)
        if ver and ver >= MIN_VERSION:
            return cargo_bin

    # 3. Check system PATH (making sure we don't recurse into ourselves)
    system_path = None if os.environ.get(_ENV_PROBING) else shutil.which(bin_name)
    if system_path:
        p = Path(system_path).resolve()
        # Avoid looping if python script itself is called pypilot.exe, or is
        # this package's own console-script launcher.
        if not str(p).lower().endswith((".py", ".pyw")) and os.path.normcase(str(p)) not in _own_launchers():
            ver = probe_binary(p)
            if ver and ver >= MIN_VERSION:
                return p

    # 4. Download latest binary
    return download_binary()
