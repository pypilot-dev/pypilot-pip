import subprocess

import pytest

import pypilot
from pypilot.binary import ensure_binary, get_platform_slug


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
