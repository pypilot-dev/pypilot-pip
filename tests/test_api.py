"""The Python API, driven by a stand-in engine (the Python interpreter)."""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path

import pytest

import pypilot
from pypilot import api

REPORT = {"pypilot": "1.2.2", "command": "doctor", "ok": True, "problems": []}


@pytest.fixture(autouse=True)
def python_as_engine(monkeypatch):
    monkeypatch.setattr(api, "ensure_binary", lambda: Path(sys.executable))


def emit(obj: object) -> list:
    return ["-c", f"import json; print(json.dumps({obj!r}))"]


def test_public_api_is_exported():
    for name in ("run", "arun", "RunResult", "ensure_binary", "get_cache_dir", "locate_engine", "__version__"):
        assert hasattr(pypilot, name)


def test_run_returns_a_completed_process():
    res = pypilot.run(emit(REPORT), capture_output=True)
    # Code written against the old return type keeps working.
    assert isinstance(res, subprocess.CompletedProcess)
    assert res.returncode == 0 and res.ok
    assert res.args[0] == sys.executable
    res.check_returncode()
    assert res.json() == REPORT


def test_run_positional_signature_is_unchanged():
    res = pypilot.run(["-c", "print('hi')"], True)
    assert res.stdout.strip() == "hi"


def test_run_does_not_raise_on_failure_unless_checked():
    res = pypilot.run(["-c", "import sys; sys.exit(3)"])
    assert res.returncode == 3 and not res.ok
    with pytest.raises(subprocess.CalledProcessError):
        pypilot.run(["-c", "import sys; sys.exit(3)"], check=True)


def test_output_is_decoded_as_utf8(monkeypatch):
    monkeypatch.setenv("PYTHONIOENCODING", "utf-8")
    res = pypilot.run(["-c", "print('\\u2713 ok')"], capture_output=True)
    assert res.stdout.strip() == "✓ ok"


def test_json_needs_captured_output():
    res = pypilot.run(["-c", "pass"])
    with pytest.raises(ValueError, match="capture_output"):
        res.json()


def test_json_reports_invalid_output():
    res = pypilot.run(["-c", "print('not json')"], capture_output=True)
    with pytest.raises(json.JSONDecodeError):
        res.json()


def test_a_string_is_not_split_into_characters():
    with pytest.raises(TypeError):
        pypilot.run("doctor")  # type: ignore[arg-type]


def test_input_cwd_and_env_are_forwarded(tmp_path):
    code = "import os, sys; print(os.getcwd()); print(os.environ['PP_TEST']); print(sys.stdin.read())"
    env = {"PP_TEST": "yes", "SYSTEMROOT": __import__("os").environ.get("SYSTEMROOT", "")}
    res = pypilot.run(["-c", code], capture_output=True, cwd=tmp_path, env=env, input="piped")
    lines = res.stdout.splitlines()
    assert Path(lines[0]).resolve() == tmp_path.resolve()
    assert lines[1:] == ["yes", "piped"]


def test_arun_matches_run():
    async def go() -> pypilot.RunResult:
        return await pypilot.arun(emit(REPORT), capture_output=True)

    res = asyncio.run(go())
    assert isinstance(res, subprocess.CompletedProcess)
    assert res.ok and res.json() == REPORT


def test_arun_check_and_input():
    async def go() -> pypilot.RunResult:
        return await pypilot.arun(
            ["-c", "import sys; print(sys.stdin.read()); sys.exit(2)"], capture_output=True, input="hi"
        )

    res = asyncio.run(go())
    assert res.returncode == 2 and res.stdout.strip() == "hi"
    with pytest.raises(subprocess.CalledProcessError):
        asyncio.run(pypilot.arun(["-c", "import sys; sys.exit(2)"], check=True))


def test_arun_timeout_kills_the_engine():
    with pytest.raises(subprocess.TimeoutExpired):
        asyncio.run(pypilot.arun(["-c", "import time; time.sleep(30)"], capture_output=True, timeout=0.5))
