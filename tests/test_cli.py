import subprocess
import sys
from pathlib import Path

import pytest

import pypilot
from pypilot import cli
from pypilot.binary import BUNDLED_VERSION, ensure_binary, get_platform_slug
from pypilot.engine import EngineInfo


def test_platform_slug():
    slug, ext = get_platform_slug()
    assert slug in ("linux-x64", "darwin-x64", "darwin-arm64", "windows-x64")
    assert ext in ("tar.gz", "zip")


@pytest.mark.network
def test_ensure_binary():
    bin_path = ensure_binary()
    assert bin_path.exists()


@pytest.mark.network
def test_pypilot_version():
    res = pypilot.run(["--version"], capture_output=True)
    assert res.returncode == 0
    assert "pypilot" in res.stdout


@pytest.mark.network
def test_wrapper_version_end_to_end():
    res = subprocess.run(
        [sys.executable, "-m", "pypilot.cli", "--version"], capture_output=True, text=True, check=False
    )
    assert res.returncode == 0, res.stderr
    # Editor extensions parse stdout as exactly `pypilot X.Y.Z`.
    assert res.stdout.strip().startswith("pypilot ")
    assert len(res.stdout.strip().splitlines()) == 1
    assert f"pypilot-cli {pypilot.__version__}" in res.stderr


class FakeRun:
    def __init__(self, stdout: str = "", returncode: int = 0) -> None:
        self.calls = []
        self.stdout = stdout
        self.returncode = returncode

    def __call__(self, cmd, **kwargs):
        self.calls.append(list(cmd))
        return subprocess.CompletedProcess(cmd, self.returncode, self.stdout, "")


def _version(monkeypatch, capsys, source: str, engine_line: str):
    info = EngineInfo(Path("/opt/engine/pypilot"), source, None)
    monkeypatch.setattr(cli, "locate_engine", lambda: info)
    fake = FakeRun(engine_line + "\n")
    monkeypatch.setattr(cli.subprocess, "run", fake)
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["--version"])
    out, err = capsys.readouterr()
    return exit_info.value.code, out, err, fake


def test_version_prints_engine_line_on_stdout_and_wrapper_on_stderr(monkeypatch, capsys):
    pinned = ".".join(map(str, BUNDLED_VERSION))
    code, out, err, fake = _version(monkeypatch, capsys, "bundled", f"pypilot {pinned}")
    assert code == 0
    assert out == f"pypilot {pinned}\n"
    assert f"pypilot-cli {pypilot.__version__} (engine: bundled," in err
    assert "warning" not in err
    assert fake.calls == [[str(Path("/opt/engine/pypilot")), "--version"]]


def test_version_warns_about_an_older_engine_on_path(monkeypatch, capsys):
    code, out, err, _ = _version(monkeypatch, capsys, "path", "pypilot 1.0.2")
    assert code == 0 and out == "pypilot 1.0.2\n"
    assert "older than" in err
    assert "from PATH" in err


def test_version_warns_about_a_different_cargo_engine(monkeypatch, capsys):
    major, minor, patch = BUNDLED_VERSION
    _, _, err, _ = _version(monkeypatch, capsys, "cargo", f"pypilot {major}.{minor}.{patch + 1}")
    assert "older than" not in err
    assert "from ~/.cargo/bin" in err


def test_version_reports_a_missing_engine(monkeypatch, capsys):
    def boom():
        raise pypilot.EngineNotFoundError("PYPILOT_OFFLINE is set")

    monkeypatch.setattr(cli, "locate_engine", boom)
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["-V"])
    out, err = capsys.readouterr()
    assert exit_info.value.code == 1 and out == ""
    assert "PYPILOT_OFFLINE is set" in err


@pytest.mark.parametrize(
    "args",
    [
        ["doctor"],
        ["completions", "bash"],
        ["--version", "--json"],
        ["doctor", "--version"],
        ["version"],
        [],
    ],
)
def test_everything_else_passes_through(monkeypatch, args):
    monkeypatch.setattr(cli, "ensure_binary", lambda: Path("engine"))
    fake = FakeRun(returncode=7)
    monkeypatch.setattr(cli.subprocess, "run", fake)
    with pytest.raises(SystemExit) as exit_info:
        cli.main(args)
    assert exit_info.value.code == 7
    assert fake.calls == [["engine", *args]]


def test_bundled_version_matches_default_tag():
    from pypilot.binary import BUNDLED_VERSION, DEFAULT_TAG, MIN_VERSION

    assert DEFAULT_TAG == "v" + ".".join(map(str, BUNDLED_VERSION))
    assert BUNDLED_VERSION >= MIN_VERSION


def test_extract_archive_reads_tar_gz_without_warnings(tmp_path):
    import io
    import tarfile
    import warnings

    from pypilot.binary import extract_archive

    archive = tmp_path / "pypilot-linux-x64.tar.gz"
    payload = b"#!/bin/sh\n"
    with tarfile.open(archive, "w:gz") as tf:
        info = tarfile.TarInfo("pypilot")
        info.size = len(payload)
        info.mode = 0o755
        tf.addfile(info, io.BytesIO(payload))

    out = tmp_path / "out"
    out.mkdir()
    with warnings.catch_warnings():
        warnings.simplefilter("error")  # 3.12/3.13 warn about the 3.14 default
        extract_archive(archive, out)
    assert (out / "pypilot").read_bytes() == payload


def test_extract_archive_reads_zip(tmp_path):
    import zipfile

    from pypilot.binary import extract_archive

    archive = tmp_path / "pypilot-windows-x64.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("pypilot.exe", b"MZ")

    out = tmp_path / "out"
    out.mkdir()
    extract_archive(archive, out)
    assert (out / "pypilot.exe").read_bytes() == b"MZ"


def test_extract_archive_refuses_members_outside_the_destination(tmp_path):
    import io
    import tarfile

    import pytest

    from pypilot.binary import extract_archive

    if not hasattr(tarfile, "data_filter"):
        pytest.skip("this Python predates tarfile extraction filters")

    archive = tmp_path / "evil.tar.gz"
    with tarfile.open(archive, "w:gz") as tf:
        info = tarfile.TarInfo("../escaped")
        info.size = 1
        tf.addfile(info, io.BytesIO(b"x"))

    out = tmp_path / "out"
    out.mkdir()
    with pytest.raises(tarfile.TarError):
        extract_archive(archive, out)
    assert not (tmp_path / "escaped").exists()


def test_install_binary_replaces_instead_of_rewriting_in_place(tmp_path):
    import os
    import sys

    from pypilot.binary import install_binary

    dest = tmp_path / "pypilot"
    dest.write_bytes(b"old engine")
    old_inode = os.stat(dest).st_ino

    src = tmp_path / "new"
    src.write_bytes(b"new engine")
    install_binary(src, dest)

    assert dest.read_bytes() == b"new engine"
    # A rename gives `dest` a new file; rewriting in place would keep the inode.
    if sys.platform != "win32":
        assert os.stat(dest).st_ino != old_inode
        assert os.access(dest, os.X_OK)
    # No temporary file is left behind.
    assert sorted(p.name for p in tmp_path.iterdir()) == ["new", "pypilot"]
