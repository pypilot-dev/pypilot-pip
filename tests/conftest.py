from __future__ import annotations

import hashlib
import io
import socket
import tarfile
import threading
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, Iterator, List

import pytest

from pypilot import engine

PROXY_VARS = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY", "REQUEST_METHOD")


def clear_proxies(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in PROXY_VARS:
        monkeypatch.delenv(name, raising=False)
        monkeypatch.delenv(name.lower(), raising=False)


@pytest.fixture
def isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Empty cache and home, nothing on PATH, no proxy.

    Any env proxy variable stops urllib from reading the Windows registry, and
    `NO_PROXY=*` keeps the local test server off any system proxy.
    """
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "cache"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    empty = tmp_path / "empty-path"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))
    for name in (engine.ENV_OFFLINE, engine.ENV_ENGINE_VERSION, engine.ENV_ALLOW_UNVERIFIED):
        monkeypatch.delenv(name, raising=False)
    clear_proxies(monkeypatch)
    monkeypatch.setenv("NO_PROXY", "*")
    return tmp_path


def make_archive(asset: str, payload: bytes) -> bytes:
    """A release archive holding a fake engine named like the real one."""
    buf = io.BytesIO()
    if asset.endswith(".zip"):
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("pypilot.exe", payload)
    else:
        with tarfile.open(fileobj=buf, mode="w:gz") as tf:
            info = tarfile.TarInfo("pypilot")
            info.size = len(payload)
            info.mode = 0o755
            tf.addfile(info, io.BytesIO(payload))
    return buf.getvalue()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class ReleaseServer:
    def __init__(self, url: str) -> None:
        self.url = url
        self.files: Dict[str, bytes] = {}
        self.requests: List[str] = []


@pytest.fixture
def release_server(isolated: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[ReleaseServer]:
    """A local stand-in for github.com release downloads: `/<tag>/<asset>`."""
    state: Dict[str, ReleaseServer] = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            server = state["s"]
            server.requests.append(self.path)
            body = server.files.get(self.path.lstrip("/"))
            if body is None:
                self.send_response(404)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args: object) -> None:
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    url = f"http://127.0.0.1:{httpd.server_address[1]}"
    state["s"] = ReleaseServer(url)
    monkeypatch.setattr(engine, "RELEASE_DOWNLOAD_URL", url + "/{tag}/{asset}")
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield state["s"]
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join()


class FakeProxy:
    """Accepts one connection, records the request line, answers 403."""

    def __init__(self, respond: bool = True) -> None:
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(1)
        self.url = f"http://127.0.0.1:{self.sock.getsockname()[1]}"
        self.request_line = ""
        self.respond = respond
        self._done = threading.Event()
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self) -> None:
        try:
            conn, _ = self.sock.accept()
        except OSError:
            return
        with conn:
            data = b""
            while b"\r\n\r\n" not in data:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                data += chunk
            self.request_line = data.split(b"\r\n", 1)[0].decode("latin-1")
            if self.respond:
                conn.sendall(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n")
            else:
                self._done.wait(10)

    def close(self) -> None:
        self._done.set()
        self.sock.close()
        self._thread.join(5)


@pytest.fixture
def fake_proxy() -> Iterator[FakeProxy]:
    proxy = FakeProxy()
    try:
        yield proxy
    finally:
        proxy.close()


@pytest.fixture
def silent_proxy() -> Iterator[FakeProxy]:
    proxy = FakeProxy(respond=False)
    try:
        yield proxy
    finally:
        proxy.close()
