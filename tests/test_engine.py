"""Locating, downloading and verifying the engine, without the network."""

from __future__ import annotations

import gc
import re
import sys
from pathlib import Path
from typing import Callable, Iterator

import pytest

from pypilot import binary, engine
from pypilot.engine import (
    EngineDownloadError,
    EngineNotFoundError,
    EngineVerificationError,
)

from conftest import ReleaseServer, clear_proxies, make_archive, sha256

ASSETS = {
    "pypilot-darwin-arm64.tar.gz",
    "pypilot-darwin-x64.tar.gz",
    "pypilot-linux-x64.tar.gz",
    "pypilot-windows-x64.zip",
}

# Before 3.11, http.client leaves the socket of a refused proxy CONNECT open
# (its `_tunnel` never closes the response). That is the standard library's
# leak, not ours. The socket sits in a reference cycle, so collect it in the
# test's own teardown, where the filter applies, not in some later test.
_tunnel_leak_filter = pytest.mark.filterwarnings(
    "ignore::ResourceWarning" if sys.version_info < (3, 11) else "error::ResourceWarning"
)


@pytest.fixture
def collect_garbage() -> Iterator[None]:
    yield
    gc.collect()


def stdlib_tunnel_leak(test: Callable[..., None]) -> Callable[..., None]:
    return pytest.mark.usefixtures("collect_garbage")(_tunnel_leak_filter(test))


def test_pin_covers_every_release_asset():
    assert set(binary.ENGINE_SHA256) == ASSETS
    for digest in binary.ENGINE_SHA256.values():
        assert re.fullmatch(r"[0-9a-f]{64}", digest)
    assert engine.asset_name() in binary.ENGINE_SHA256


def test_pin_is_a_plain_text_assignment_in_binary_py():
    # The release-coordination workflow edits these lines of binary.py.
    source = Path(binary.__file__).read_text(encoding="utf-8")
    assert re.search(r'^DEFAULT_TAG = "v\d+\.\d+\.\d+"$', source, re.M)
    for asset, digest in binary.ENGINE_SHA256.items():
        assert f'    "{asset}": "{digest}",\n' in source


def test_binary_module_still_exports_the_old_names():
    from pypilot.binary import (  # noqa: F401
        download_binary,
        ensure_binary,
        extract_archive,
        get_cache_dir,
        get_platform_slug,
        install_binary,
        parse_version,
        probe_binary,
    )

    assert ensure_binary is engine.ensure_binary
    with pytest.raises(AttributeError):
        binary.no_such_name  # noqa: B018


def test_parse_sha256sums():
    text = "# comment\n" + "a" * 64 + "  pypilot-linux-x64.tar.gz\n" + "B" * 64 + " *pypilot-windows-x64.zip\n\n"
    assert engine.parse_sha256sums(text) == {
        "pypilot-linux-x64.tar.gz": "a" * 64,
        "pypilot-windows-x64.zip": "b" * 64,
    }


def test_requested_tag_normalises(monkeypatch):
    monkeypatch.setenv(engine.ENV_ENGINE_VERSION, "1.3.0")
    assert engine.requested_tag() == "v1.3.0"
    monkeypatch.setenv(engine.ENV_ENGINE_VERSION, " v1.3.0 ")
    assert engine.requested_tag() == "v1.3.0"
    monkeypatch.setenv(engine.ENV_ENGINE_VERSION, "")
    assert engine.requested_tag() is None


def _serve_pinned(server: ReleaseServer, monkeypatch, payload: bytes = b"engine") -> bytes:
    asset = engine.asset_name()
    data = make_archive(asset, payload)
    server.files[f"{binary.DEFAULT_TAG}/{asset}"] = data
    monkeypatch.setitem(engine.ENGINE_SHA256, asset, sha256(data))
    return data


def test_pinned_download_is_verified_and_cached(release_server, monkeypatch):
    _serve_pinned(release_server, monkeypatch, b"good engine")
    path = engine.download_binary()
    assert path.read_bytes() == b"good engine"
    assert path.parent == engine.get_cache_dir() / binary.DEFAULT_TAG


def test_hash_mismatch_deletes_the_download_and_raises(release_server, monkeypatch, tmp_path):
    _serve_pinned(release_server, monkeypatch)
    monkeypatch.setitem(engine.ENGINE_SHA256, engine.asset_name(), "0" * 64)
    out = tmp_path / "dl"
    out.mkdir()
    with pytest.raises(EngineVerificationError, match="SHA-256 mismatch"):
        engine.download_verified_archive(binary.DEFAULT_TAG, engine.asset_name(), out)
    assert list(out.iterdir()) == []
    assert not (engine.get_cache_dir() / binary.DEFAULT_TAG / engine.binary_name()).exists()


def test_pinned_asset_without_a_hash_is_refused(release_server, monkeypatch):
    _serve_pinned(release_server, monkeypatch)
    monkeypatch.delitem(engine.ENGINE_SHA256, engine.asset_name())
    with pytest.raises(EngineVerificationError, match="pins no SHA-256"):
        engine.download_binary()
    assert release_server.requests == []


def test_override_is_verified_against_sha256sums(release_server, monkeypatch):
    asset = engine.asset_name()
    data = make_archive(asset, b"override engine")
    release_server.files[f"v9.9.9/{asset}"] = data
    release_server.files["v9.9.9/SHA256SUMS"] = f"{sha256(data)}  {asset}\n".encode()
    path = engine.download_binary("v9.9.9")
    assert path.read_bytes() == b"override engine"
    assert path.parent.name == "v9.9.9"


def test_override_with_a_wrong_sum_is_refused(release_server):
    asset = engine.asset_name()
    release_server.files[f"v9.9.9/{asset}"] = make_archive(asset, b"x")
    release_server.files["v9.9.9/SHA256SUMS"] = f"{'1' * 64}  {asset}\n".encode()
    with pytest.raises(EngineVerificationError, match="mismatch"):
        engine.download_binary("v9.9.9")


def test_override_missing_from_sha256sums_is_refused(release_server):
    release_server.files["v9.9.9/SHA256SUMS"] = b"%s  other-asset.zip\n" % (b"1" * 64)
    with pytest.raises(EngineVerificationError, match="no entry"):
        engine.download_binary("v9.9.9")


def test_release_without_sha256sums_needs_explicit_opt_in(release_server, monkeypatch, capsys):
    asset = engine.asset_name()
    release_server.files[f"v1.0.9/{asset}"] = make_archive(asset, b"old engine")
    with pytest.raises(EngineVerificationError, match="PYPILOT_ALLOW_UNVERIFIED"):
        engine.download_binary("v1.0.9")
    assert f"/v1.0.9/{asset}" not in release_server.requests

    monkeypatch.setenv(engine.ENV_ALLOW_UNVERIFIED, "1")
    path = engine.download_binary("v1.0.9")
    assert path.read_bytes() == b"old engine"
    assert "UNVERIFIED" in capsys.readouterr().err


def test_offline_never_downloads(isolated, monkeypatch):
    def no_download(*args, **kwargs):
        raise AssertionError("downloaded while offline")

    monkeypatch.setattr(engine, "_download", no_download)
    monkeypatch.setenv(engine.ENV_OFFLINE, "1")
    with pytest.raises(EngineNotFoundError, match="PYPILOT_OFFLINE is set"):
        engine.locate_engine()
    monkeypatch.setenv(engine.ENV_ENGINE_VERSION, "v9.9.9")
    with pytest.raises(EngineNotFoundError, match="PYPILOT_OFFLINE is set"):
        engine.locate_engine()


def test_probing_never_searches_path(isolated, monkeypatch, tmp_path):
    # A `pypilot` on PATH may be this wrapper; probing it must not recurse.
    fake = tmp_path / "empty-path" / engine.binary_name()
    fake.write_bytes(b"x")
    monkeypatch.setenv(engine._ENV_PROBING, "1")
    assert engine._from_path() is None


@stdlib_tunnel_leak
def test_proxy_from_the_environment_is_used(isolated, monkeypatch, fake_proxy, tmp_path):
    clear_proxies(monkeypatch)
    monkeypatch.setenv("HTTPS_PROXY", fake_proxy.url)
    with pytest.raises(EngineDownloadError) as err:
        engine._download("https://github.com/pypilot-dev/pypilot/releases/x", tmp_path / "x")
    assert fake_proxy.request_line.startswith("CONNECT github.com:443 HTTP/")
    message = str(err.value)
    assert f"through proxy {fake_proxy.url}" in message
    assert "HTTPS_PROXY" in message and "NO_PROXY" in message


def test_no_proxy_bypasses_the_proxy(isolated, monkeypatch):
    import urllib.request

    clear_proxies(monkeypatch)
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:9")
    monkeypatch.setenv("NO_PROXY", "github.com")
    assert urllib.request.proxy_bypass("github.com")
    assert not urllib.request.proxy_bypass("example.org")


@stdlib_tunnel_leak
@pytest.mark.skipif(sys.platform != "win32", reason="Windows registry proxy")
def test_windows_registry_proxy_is_used(isolated, monkeypatch, fake_proxy, tmp_path):
    import urllib.request

    clear_proxies(monkeypatch)
    # What urllib reads from Internet Settings when no env variable is set.
    monkeypatch.setattr(urllib.request, "getproxies_registry", lambda: {"https": fake_proxy.url})
    monkeypatch.setattr(urllib.request, "proxy_bypass_registry", lambda host: False)
    with pytest.raises(EngineDownloadError, match="through proxy"):
        engine._download("https://github.com/pypilot-dev/pypilot/releases/x", tmp_path / "x")
    assert fake_proxy.request_line.startswith("CONNECT github.com:443 HTTP/")


@stdlib_tunnel_leak
def test_download_times_out_with_a_clear_error(isolated, monkeypatch, silent_proxy, tmp_path):
    clear_proxies(monkeypatch)
    monkeypatch.setenv("HTTPS_PROXY", silent_proxy.url)
    monkeypatch.setenv(engine.ENV_DOWNLOAD_TIMEOUT, "0.5")
    with pytest.raises(EngineDownloadError, match=r"timeout is 0\.5s"):
        engine._download("https://github.com/pypilot-dev/pypilot/releases/x", tmp_path / "x")


def test_proxy_password_is_not_printed():
    assert engine._redact("http://me:secret@proxy:8080") == "http://me:***@proxy:8080"
    assert engine._redact("http://proxy:8080") == "http://proxy:8080"


def test_http_errors_carry_their_status(release_server, tmp_path):
    with pytest.raises(EngineDownloadError) as err:
        engine._download(release_server.url + "/missing", tmp_path / "x")
    assert err.value.status == 404
