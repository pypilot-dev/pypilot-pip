"""
pypilot.engine: locate, download and verify the native `pypilot` engine.

Lookup order (first match wins), see `locate_engine`:

1. `PYPILOT_ENGINE_VERSION=vX.Y.Z` set: that release only, from the cache or
   downloaded and checked against the release's `SHA256SUMS`.
2. A previous verified download of the pinned release in the cache.
3. `~/.cargo/bin/pypilot` (a source build), if at least `MIN_VERSION`.
4. A `pypilot` engine on PATH, if at least `MIN_VERSION`.
5. Download the pinned release, verified against `ENGINE_SHA256`, unless
   `PYPILOT_OFFLINE` is set.
"""

from __future__ import annotations

import hashlib
import os
import platform
import shutil
import stat
import subprocess
import sys
import sysconfig
import tarfile
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Set, Tuple, Union

from .binary import BUNDLED_VERSION, DEFAULT_TAG, ENGINE_SHA256, GITHUB_REPO, MIN_VERSION

Version = Tuple[int, int, int]
StrPath = Union[str, "os.PathLike[str]"]

RELEASE_DOWNLOAD_URL = "https://github.com/{repo}/releases/download/{tag}/{asset}"
SHA256SUMS_ASSET = "SHA256SUMS"
DEFAULT_DOWNLOAD_TIMEOUT = 60.0

ENV_OFFLINE = "PYPILOT_OFFLINE"
ENV_ENGINE_VERSION = "PYPILOT_ENGINE_VERSION"
ENV_ALLOW_UNVERIFIED = "PYPILOT_ALLOW_UNVERIFIED"
ENV_DOWNLOAD_TIMEOUT = "PYPILOT_DOWNLOAD_TIMEOUT"
# Set while probing a candidate engine. A `pypilot` on PATH can be this very
# wrapper (a console-script launcher), and probing it must not make it search
# PATH again or download anything.
_ENV_PROBING = "_PYPILOT_PROBING"

# Values of `EngineInfo.source`.
SOURCE_OVERRIDE = "override"
SOURCE_CACHE = "cache"
SOURCE_CARGO = "cargo"
SOURCE_PATH = "path"
SOURCE_DOWNLOAD = "download"


class EngineError(RuntimeError):
    """The native engine could not be located, downloaded or verified."""


class EngineNotFoundError(EngineError):
    """No engine is available and none may be downloaded."""


class EngineDownloadError(EngineError):
    """A release file could not be fetched."""

    def __init__(self, message: str, status: Optional[int] = None) -> None:
        super().__init__(message)
        self.status = status


class EngineVerificationError(EngineError):
    """A download did not match its expected SHA-256, or could not be checked."""


@dataclass(frozen=True)
class EngineInfo:
    """Where the engine was found and which version it reports."""

    path: Path
    source: str
    version: Optional[Version] = None


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def is_offline() -> bool:
    """True when `PYPILOT_OFFLINE` forbids every download."""
    return _env_flag(ENV_OFFLINE)


def get_platform_slug() -> Tuple[str, str]:
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


def asset_name() -> str:
    """The release asset for this platform, e.g. `pypilot-windows-x64.zip`."""
    slug, ext = get_platform_slug()
    return f"pypilot-{slug}.{ext}"


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


def cache_dir_for(tag: str) -> Path:
    """Cache directory for one release. Versioned, so two installs of
    pypilot-cli pinned to different engines never fight over one file."""
    path = get_cache_dir() / tag
    path.mkdir(parents=True, exist_ok=True)
    return path


def binary_name() -> str:
    return "pypilot.exe" if sys.platform == "win32" else "pypilot"


def parse_version(out: str) -> Optional[Version]:
    # Example: "pypilot 1.0.2"
    for part in out.strip().split():
        components = part.split(".")
        if len(components) == 3 and all(c.isdigit() for c in components):
            return int(components[0]), int(components[1]), int(components[2])
    return None


def tag_version(tag: str) -> Optional[Version]:
    return parse_version(tag.lstrip("v"))


def probe_binary(path: StrPath) -> Optional[Version]:
    env = dict(os.environ)
    env[_ENV_PROBING] = "1"
    env[ENV_OFFLINE] = "1"
    try:
        res = subprocess.run(
            [os.fspath(path), "--version"],
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


def extract_archive(archive: StrPath, dest: StrPath) -> None:
    """Extract a downloaded `.zip` or `.tar.gz` release archive into `dest`."""
    if os.fspath(archive).endswith(".zip"):
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


# ---------------------------------------------------------------------------
# Downloading and verification


def release_url(tag: str, asset: str) -> str:
    return RELEASE_DOWNLOAD_URL.format(repo=GITHUB_REPO, tag=tag, asset=asset)


def download_timeout() -> float:
    raw = os.environ.get(ENV_DOWNLOAD_TIMEOUT, "").strip()
    try:
        value = float(raw) if raw else DEFAULT_DOWNLOAD_TIMEOUT
    except ValueError:
        return DEFAULT_DOWNLOAD_TIMEOUT
    return value if value > 0 else DEFAULT_DOWNLOAD_TIMEOUT


def _redact(url: str) -> str:
    """Drop a password from a proxy URL before it goes into a message."""
    try:
        parts = urllib.parse.urlsplit(url)
    except ValueError:
        return url
    if parts.password is None:
        return url
    host = parts.hostname or ""
    if parts.port:
        host = f"{host}:{parts.port}"
    netloc = f"{parts.username}:***@{host}" if parts.username else host
    return urllib.parse.urlunsplit(parts._replace(netloc=netloc))


def _network_hint(url: str, reason: object, timeout: float) -> str:
    # The same lookup urllib's ProxyHandler does: HTTPS_PROXY / NO_PROXY first,
    # then the Windows registry or macOS system settings.
    proxies = urllib.request.getproxies()
    host = urllib.parse.urlsplit(url).hostname or ""
    proxy = proxies.get(urllib.parse.urlsplit(url).scheme)
    if proxy and not urllib.request.proxy_bypass(host):
        route = f"through proxy {_redact(proxy)}"
    else:
        route = "with no proxy"
    return (
        f"could not download {url} ({route}): {reason}. "
        "Behind a proxy, set HTTPS_PROXY (and NO_PROXY for hosts that must "
        "bypass it); the system proxy settings are used when those are unset. "
        f"The timeout is {timeout:g}s ({ENV_DOWNLOAD_TIMEOUT}). To avoid the "
        "download, build the engine with `cargo install --path helper` or put "
        "a `pypilot` engine on PATH."
    )


def _download(url: str, dest: Path) -> None:
    """Fetch `url` into `dest`, honouring the environment's proxy settings."""
    timeout = download_timeout()
    request = urllib.request.Request(url, headers={"User-Agent": "pypilot-python"})
    # A fresh opener per download: `urlopen` caches one built from the proxy
    # settings at its first call.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler())
    try:
        with opener.open(request, timeout=timeout) as resp, open(dest, "wb") as out:
            shutil.copyfileobj(resp, out)
    except urllib.error.HTTPError as e:
        e.close()  # it holds the open response
        raise EngineDownloadError(f"{url} returned HTTP {e.code} {e.reason}", status=e.code) from e
    except (urllib.error.URLError, OSError) as e:
        reason = getattr(e, "reason", None) or e
        raise EngineDownloadError(_network_hint(url, reason, timeout)) from e


def sha256_file(path: StrPath) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_sha256sums(text: str) -> Dict[str, str]:
    """Parse `<sha256>  <asset-name>` lines (the `sha256sum` format)."""
    sums: Dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        # `sha256sum -b` marks binary mode with a leading `*`.
        sums[parts[-1].lstrip("*")] = parts[0].lower()
    return sums


def _offline_error(what: str) -> EngineNotFoundError:
    return EngineNotFoundError(
        f"{ENV_OFFLINE} is set, so PyPilot will not download {what}, and no "
        "engine is available locally. Build it with `cargo install --path helper`, "
        f"put a `pypilot` engine on PATH, or unset {ENV_OFFLINE}."
    )


def expected_sha256(tag: str, asset: str) -> Optional[str]:
    """The SHA-256 `asset` of `tag` must have, or None if it may run unverified.

    The pinned release is checked against `ENGINE_SHA256`; any other release
    against its own `SHA256SUMS` asset. A release without one is refused
    unless `PYPILOT_ALLOW_UNVERIFIED` is set.
    """
    if tag == DEFAULT_TAG:
        digest = ENGINE_SHA256.get(asset)
        if digest is None:
            raise EngineVerificationError(
                f"pypilot-cli pins no SHA-256 for {asset} of {tag}, so it cannot be verified"
            )
        return digest.lower()

    if is_offline():
        raise _offline_error(f"{SHA256SUMS_ASSET} of {tag}")
    with tempfile.TemporaryDirectory() as tmpdir:
        sums_path = Path(tmpdir) / SHA256SUMS_ASSET
        try:
            _download(release_url(tag, SHA256SUMS_ASSET), sums_path)
        except EngineDownloadError as e:
            if e.status != 404:
                raise
            sums = None
        else:
            sums = parse_sha256sums(sums_path.read_text(encoding="utf-8", errors="replace"))

    if sums is not None:
        digest = sums.get(asset)
        if digest is None:
            raise EngineVerificationError(f"{SHA256SUMS_ASSET} of {tag} has no entry for {asset}")
        return digest

    if _env_flag(ENV_ALLOW_UNVERIFIED):
        print(
            f"PyPilot: warning: release {tag} publishes no {SHA256SUMS_ASSET}; "
            f"running {asset} UNVERIFIED because {ENV_ALLOW_UNVERIFIED} is set.",
            file=sys.stderr,
        )
        return None
    raise EngineVerificationError(
        f"release {tag} publishes no {SHA256SUMS_ASSET}, so {asset} cannot be verified. "
        f"Set {ENV_ALLOW_UNVERIFIED}=1 to run it anyway, or unset {ENV_ENGINE_VERSION} "
        f"to use the pinned {DEFAULT_TAG}."
    )


def download_verified_archive(tag: str, asset: str, dest_dir: StrPath) -> Path:
    """Download `asset` of release `tag` into `dest_dir` and check its SHA-256.

    On a mismatch the file is deleted and `EngineVerificationError` raised, so
    nothing unverified is ever extracted or run.
    """
    if is_offline():
        raise _offline_error(f"{asset} of {tag}")
    expected = expected_sha256(tag, asset)
    url = release_url(tag, asset)
    archive = Path(dest_dir) / asset
    print(f"PyPilot: downloading native engine from {url} ...", file=sys.stderr)
    _download(url, archive)
    if expected is not None:
        actual = sha256_file(archive)
        if actual != expected:
            archive.unlink()
            raise EngineVerificationError(
                f"SHA-256 mismatch for {url}: expected {expected}, got {actual}. "
                "The download was deleted without being run. Retry; if it keeps "
                "failing, something between you and GitHub is altering the file."
            )
    return archive


def download_binary(tag: str = DEFAULT_TAG) -> Path:
    """Download, verify and cache the engine of release `tag`."""
    asset = asset_name()
    bin_name = binary_name()
    dest_binary = cache_dir_for(tag) / bin_name

    with tempfile.TemporaryDirectory() as tmpdir:
        archive = download_verified_archive(tag, asset, tmpdir)
        out = Path(tmpdir) / "extracted"
        out.mkdir()
        extract_archive(archive, out)

        extracted_bin = out / bin_name
        if not extracted_bin.exists():
            candidates = list(out.rglob(bin_name))
            if not candidates:
                raise FileNotFoundError(f"{bin_name} not found in downloaded archive {asset}")
            extracted_bin = candidates[0]

        install_binary(extracted_bin, dest_binary)

    return dest_binary


# ---------------------------------------------------------------------------
# Lookup


def requested_tag() -> Optional[str]:
    """The release `PYPILOT_ENGINE_VERSION` asks for, normalised to `vX.Y.Z`."""
    raw = os.environ.get(ENV_ENGINE_VERSION, "").strip()
    if not raw:
        return None
    return raw if raw.startswith("v") else f"v{raw}"


def _cached(tag: str) -> Optional[EngineInfo]:
    path = cache_dir_for(tag) / binary_name()
    if not path.is_file():
        return None
    version = probe_binary(path)
    wanted = tag_version(tag)
    if version is None or (wanted is not None and version != wanted):
        return None
    return EngineInfo(path, SOURCE_CACHE, version)


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


def _from_path() -> Optional[EngineInfo]:
    if os.environ.get(_ENV_PROBING):
        return None
    system_path = shutil.which(binary_name())
    if not system_path:
        return None
    path = Path(system_path).resolve()
    if str(path).lower().endswith((".py", ".pyw")):
        return None
    if os.path.normcase(str(path)) in _own_launchers():
        return None
    version = probe_binary(path)
    if version and version >= MIN_VERSION:
        return EngineInfo(path, SOURCE_PATH, version)
    return None


def locate_engine() -> EngineInfo:
    """Find the engine (downloading it if allowed); see the module docstring."""
    override = requested_tag()
    if override:
        hit = _cached(override)
        if hit is not None:
            return EngineInfo(hit.path, SOURCE_OVERRIDE, hit.version)
        path = download_binary(override)
        return EngineInfo(path, SOURCE_OVERRIDE, probe_binary(path))

    hit = _cached(DEFAULT_TAG)
    if hit is not None:
        return hit

    cargo_bin = Path.home() / ".cargo" / "bin" / binary_name()
    if cargo_bin.is_file():
        version = probe_binary(cargo_bin)
        if version and version >= MIN_VERSION:
            return EngineInfo(cargo_bin, SOURCE_CARGO, version)

    on_path = _from_path()
    if on_path is not None:
        return on_path

    if is_offline():
        raise _offline_error("the engine")
    return EngineInfo(download_binary(), SOURCE_DOWNLOAD, BUNDLED_VERSION)


def ensure_binary() -> Path:
    """Path to a usable engine, downloading it if needed and allowed."""
    return locate_engine().path
