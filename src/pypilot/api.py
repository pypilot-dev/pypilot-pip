"""
pypilot.api: run the engine from Python.

`run` keeps its old behaviour: it returns a `subprocess.CompletedProcess`
(now the `RunResult` subclass, which adds `.ok` and `.json()`), never raises
for a non-zero exit unless `check=True`, and leaves output on the terminal
unless `capture_output=True`.
"""

from __future__ import annotations

import asyncio
import json as _json
import subprocess
from typing import TYPE_CHECKING, Any, List, Mapping, Optional, Sequence

from .engine import StrPath, ensure_binary

if TYPE_CHECKING:
    _CompletedProcess = subprocess.CompletedProcess[str]
else:
    # Not subscriptable at runtime before Python 3.9.
    _CompletedProcess = subprocess.CompletedProcess

# The engine always writes UTF-8, whatever the locale says.
_ENCODING = "utf-8"
_ERRORS = "replace"


class RunResult(_CompletedProcess):
    """The outcome of one engine invocation.

    A `subprocess.CompletedProcess`, so existing code using `.returncode`,
    `.stdout`, `.stderr`, `.args` or `.check_returncode()` keeps working.
    """

    @property
    def ok(self) -> bool:
        return self.returncode == 0

    def json(self) -> Any:
        """Parse the `--json` output of a command.

        Every command's JSON has the shape
        `{"pypilot": ..., "command": ..., "ok": ..., ...}`. Requires
        `capture_output=True`.
        """
        if self.stdout is None:
            raise ValueError("stdout was not captured; call run(..., capture_output=True)")
        return _json.loads(self.stdout)


def _command(args: Optional[Sequence[str]]) -> List[str]:
    if isinstance(args, str):
        raise TypeError("args must be a list of strings, e.g. ['doctor', '--json']")
    return [str(ensure_binary()), *(args or [])]


async def _kill(proc: asyncio.subprocess.Process) -> None:
    if proc.returncode is None:
        try:
            proc.kill()
        except ProcessLookupError:
            pass
    # Read the pipes to EOF, not just wait(): otherwise the loop can close
    # with their transports still open (a ResourceWarning on Windows 3.8).
    await proc.communicate()


def run(
    args: Optional[Sequence[str]] = None,
    capture_output: bool = False,
    check: bool = False,
    *,
    cwd: Optional[StrPath] = None,
    env: Optional[Mapping[str, str]] = None,
    input: Optional[str] = None,
    timeout: Optional[float] = None,
) -> RunResult:
    """
    Run PyPilot programmatically.

    Example:
        import pypilot
        res = pypilot.run(["doctor", "--json"], capture_output=True)
        report = res.json()

    `check=True` raises `subprocess.CalledProcessError` on a non-zero exit.
    """
    cmd = _command(args)
    proc = subprocess.run(
        cmd,
        capture_output=capture_output,
        encoding=_ENCODING,
        errors=_ERRORS,
        check=False,
        cwd=cwd,
        env=dict(env) if env is not None else None,
        input=input,
        timeout=timeout,
    )
    result = RunResult(proc.args, proc.returncode, proc.stdout, proc.stderr)
    if check:
        result.check_returncode()
    return result


async def arun(
    args: Optional[Sequence[str]] = None,
    capture_output: bool = False,
    check: bool = False,
    *,
    cwd: Optional[StrPath] = None,
    env: Optional[Mapping[str, str]] = None,
    input: Optional[str] = None,
    timeout: Optional[float] = None,
) -> RunResult:
    """`run`, without blocking the event loop.

    Locating (and possibly downloading) the engine happens in a worker thread.
    On timeout the engine is killed and `subprocess.TimeoutExpired` raised.
    """
    loop = asyncio.get_running_loop()
    cmd = await loop.run_in_executor(None, _command, args)
    pipe = asyncio.subprocess.PIPE if capture_output else None
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.PIPE if input is not None else None,
        stdout=pipe,
        stderr=pipe,
        cwd=cwd,
        env=dict(env) if env is not None else None,
    )
    data = input.encode(_ENCODING) if input is not None else None
    try:
        out, err = await asyncio.wait_for(proc.communicate(data), timeout)
    except asyncio.TimeoutError:
        await _kill(proc)
        raise subprocess.TimeoutExpired(cmd, timeout or 0) from None
    except asyncio.CancelledError:
        await _kill(proc)
        raise

    def decode(raw: Optional[bytes]) -> Optional[str]:
        return raw.decode(_ENCODING, _ERRORS) if raw is not None else None

    assert proc.returncode is not None
    result = RunResult(cmd, proc.returncode, decode(out), decode(err))
    if check:
        result.check_returncode()
    return result
