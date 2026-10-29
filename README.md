# PyPilot (CLI & Python Package)

<p align="center">
  <a href="https://pypi.org/project/pypilot-cli/"><img src="https://img.shields.io/pypi/v/pypilot-cli?color=blue&logo=pypi&logoColor=white" alt="PyPI version" /></a>
  <a href="https://pypi.org/project/pypilot-cli/"><img src="https://img.shields.io/pypi/pyversions/pypilot-cli?logo=python&logoColor=white" alt="Supported Python versions" /></a>
  <a href="https://pypi.org/project/pypilot-cli/"><img src="https://img.shields.io/pypi/dm/pypilot-cli?color=2ea44f" alt="Monthly downloads" /></a>
  <a href="https://github.com/pypilot-dev/pypilot-pip/blob/master/LICENSE"><img src="https://img.shields.io/pypi/l/pypilot-cli?color=blue" alt="License: AGPL-3.0-or-later" /></a>
  <a href="https://github.com/pypilot-dev/pypilot"><img src="https://img.shields.io/badge/engine-Rust-orange?logo=rust&logoColor=white" alt="Rust engine" /></a>
  <a href="https://github.com/pypilot-dev/pypilot"><img src="https://img.shields.io/github/stars/pypilot-dev/pypilot?style=social" alt="GitHub stars" /></a>
</p>

> ⭐ **Enjoying PyPilot?** If it saved you from a broken environment, please [star it on GitHub](https://github.com/pypilot-dev/pypilot). It's free and it helps other Python developers find it.

**PyPilot** is a deterministic Python environment doctor, dependency solver, and toolchain manager. Powered by a high-speed compiled **Rust engine**, PyPilot calculates dependency intersections directly from PyPI wheel metadata, resolves hardware and CUDA build compatibility, and sets up working virtual environments without external AI or API keys.

---

## ⚡ High-Speed Native Rust Architecture

PyPilot combines the ease of installation via `pip` with the raw execution speed and low memory footprint of compiled Rust:
- **Instant startup**: Binary execution starts in single-digit milliseconds.
- **Zero Python overhead**: CLI commands delegate directly to the native `pypilot` binary.
- **Engine included**: the wheels for Linux `x86_64`, macOS `Apple Silicon` / `Intel` and Windows `x64` bundle the native engine, so `pip install` is all it takes and nothing is downloaded at run time. On other platforms the engine is downloaded once, checked against a pinned SHA-256, and cached; a system-installed Rust binary on your `$PATH` is respected.

---

## 📥 Installation

Install via `pip`:
```bash
pip install pypilot-cli
```

Or install as an isolated global tool with `uv`:
```bash
uv tool install pypilot-cli
```

Or via `pipx`:
```bash
pipx install pypilot-cli
```

pip picks the right wheel for you:

| Platform | Wheel | Engine |
|---|---|---|
| Linux x86_64, glibc 2.34 or newer (Ubuntu 22.04+, Debian 12+, RHEL/Alma/Rocky 9+, Fedora 35+) | `manylinux_2_34_x86_64` | bundled |
| macOS 11+ on Apple Silicon | `macosx_11_0_arm64` | bundled |
| macOS 10.12+ on Intel | `macosx_10_12_x86_64` | bundled |
| Windows x64 | `win_amd64` | bundled |
| Anything else (older glibc, other CPUs) | `py3-none-any` | downloaded on first use, if a release exists for the platform |

There is no musl (Alpine) build of the engine. On Linux with an older glibc, build the engine from source (`cargo install --path helper` in the [engine repo](https://github.com/pypilot-dev/pypilot)) and the wrapper will find it in `~/.cargo/bin`.

---

## 📖 CLI Reference & Commands

PyPilot provides a complete suite of environment doctor and bootstrap tools:

### 1. `pypilot doctor`
Analyzes your current workspace, virtual environment, and dependency manifests (`requirements.txt`, `pyproject.toml`, `environment.yml`). Displays a read-only health check without modifying any files.
```bash
pypilot doctor
# Target a specific workspace folder:
pypilot doctor --path /path/to/project
```

### 2. `pypilot setup`
Bootstraps a deterministic virtual environment. Automatically detects existing system tools:
- Uses system `uv` if present on `$PATH`.
- Supports **pip-compatible mode** (`uv venv` + `uv pip`) to accelerate installations without forcing a `pyproject.toml` migration.
- Falls back cleanly to standard `python -m venv` + `pip` if `uv` is not installed.
```bash
pypilot setup
```

### 3. `pypilot check <package>`
Verifies whether a specific package and its wheels support your project's current Python interpreter version and operating system.
```bash
pypilot check mediapipe
pypilot check torch
pypilot check tensorflow
```

### 4. `pypilot install <package>`
Installs a package into your virtual environment and records it in your manifest (`requirements.txt` or `pyproject.toml`), preserving version constraints.
```bash
pypilot install requests
pypilot install numpy
```

### 5. `pypilot fix python`
Recomputes dependency version intersection and rebuilds the virtual environment on a Python version supported by all dependencies.
```bash
pypilot fix python
```

### 6. `pypilot fix cuda`
Scans system NVIDIA driver version and CUDA runtime, then re-pins PyTorch or TensorFlow wheels to the exact hardware-matched CUDA build.
```bash
pypilot fix cuda
```

### 7. `pypilot update-data`
Forces an immediate update of bundled hardware driver, CUDA compatibility matrices, and package wheel metadata.
```bash
pypilot update-data
```

### 8. `pypilot migrate-conda`
Translates legacy Anaconda / Miniconda `environment.yml` configuration files into a standard modern `pyproject.toml`.
```bash
pypilot migrate-conda
```

### 9. `pypilot lsp`
Runs PyPilot as a Language Server Protocol (LSP) server over `stdio`. Used natively by editor extensions ([Zed](https://zed.dev) and [VS Code](https://marketplace.visualstudio.com/items?itemName=AbdullahMasood-005.pypilot-vscode)) for live import diagnostics and automated environment actions.
```bash
pypilot lsp
```

### 10. `pypilot --version`
Prints the engine's version (`pypilot X.Y.Z`) on stdout, which is what editor extensions read, and the wrapper's own line on stderr: `pypilot-cli X.Y.Z (engine: <where>, <path>)`. `<where>` is `bundled`, `cache`, `download`, `cargo`, `path` or `override`. It also warns when the engine in use is older than the one this release of `pypilot-cli` pins, or comes from `~/.cargo/bin` / `PATH` with a different version.

### 11. `pypilot completions <shell>`
Prints a shell completion script (generated by the engine), e.g. `pypilot completions bash > ~/.local/share/bash-completion/completions/pypilot`. Every argument except a lone `--version` / `-V` goes to the engine unchanged.

---

## 🐍 Python Programmatic API

PyPilot can also be imported and used directly inside Python code:

```python
import pypilot

# Run any PyPilot command programmatically
result = pypilot.run(["doctor"], capture_output=True)
print(result.returncode, result.stdout)

# Commands with --json print {"pypilot": ..., "command": ..., "ok": ..., ...}
report = pypilot.run(["doctor", "--json"], capture_output=True).json()

# Raise subprocess.CalledProcessError on a non-zero exit
pypilot.run(["check", "torch"], check=True)

# Locate or ensure native engine is available
bin_path = pypilot.ensure_binary()
info = pypilot.locate_engine()  # EngineInfo(path, source, version)
```

From async code, `await pypilot.arun([...])` takes the same arguments and does not block the event loop.

- `run(args=None, capture_output=False, check=False, *, cwd=None, env=None, input=None, timeout=None)` returns a `RunResult`, a subclass of `subprocess.CompletedProcess`, so `.returncode`, `.stdout`, `.stderr` and `.check_returncode()` work as before. It adds `.ok` and `.json()`. Output is decoded as UTF-8, which is what the engine writes.
- Without `check=True` a failing command does not raise. Look at `.returncode`.
- Engine problems raise `pypilot.EngineError` subclasses: `EngineNotFoundError` (offline and no engine), `EngineDownloadError`, `EngineVerificationError`.
- The package ships `py.typed`, so type checkers see these signatures.

---

## ⚙️ Configuration

PyPilot respects workspace settings in `.pypilot.toml` or your editor configuration:
- `package_manager`: `"auto"` (default), `"uv"`, `"uv-pip"`, `"pip"`, or `"pixi"` (manage with pixi; a project without a pixi manifest gets a `pixi.toml` from setup). pixi projects are detected whatever this says.
- `notifications`: `"all"`, `"problems-only"`, or `"off"`.

---

## 🔒 The native engine: lookup, verification, offline and proxies

**Where the engine comes from.** The first match wins:

1. `PYPILOT_ENGINE_VERSION=vX.Y.Z`, if set: that engine release, from the cache or downloaded (for testing other engines).
2. The engine bundled in a platform wheel (`site-packages/pypilot/_engine/`).
3. An earlier verified download of the pinned release, in the cache: `%LOCALAPPDATA%\pypilot\bin\<tag>\` on Windows, `$XDG_CACHE_HOME/pypilot/bin/<tag>/` (default `~/.cache/...`) elsewhere.
4. `~/.cargo/bin/pypilot`, a source build, if it is at least 1.0.2.
5. A `pypilot` engine on `PATH`, if it is at least 1.0.2. The wrapper skips its own `pypilot` launcher.
6. A download of the pinned release, unless offline mode is on.

**Verification.** Each `pypilot-cli` release pins one engine release (`DEFAULT_TAG` in `pypilot/binary.py`) and the SHA-256 of each of its archives (`ENGINE_SHA256`). A download is checked before it is extracted or run. On a mismatch the file is deleted and the command fails with `SHA-256 mismatch`. With `PYPILOT_ENGINE_VERSION`, the archive is checked against that release's `SHA256SUMS` file instead. A release without one is refused unless you also set `PYPILOT_ALLOW_UNVERIFIED=1`, which prints a warning. The bundled wheels contain the same verified binaries.

**Offline.** `PYPILOT_OFFLINE=1` forbids every download. If no engine is available locally, PyPilot fails at once and tells you so, without waiting on the network. With a platform wheel, offline mode just works.

**Proxies.** Downloads use the standard proxy settings: `HTTPS_PROXY` / `HTTP_PROXY` and `NO_PROXY` (either case), or, when none is set, the system settings (Windows Internet Options, macOS network settings). A failed download says which proxy it went through. `PYPILOT_DOWNLOAD_TIMEOUT` sets the network timeout in seconds (default 60).

| Variable | Effect |
|---|---|
| `PYPILOT_OFFLINE=1` | Never download; fail fast if no engine is available |
| `PYPILOT_ENGINE_VERSION=vX.Y.Z` | Use this engine release instead of the pinned one |
| `PYPILOT_ALLOW_UNVERIFIED=1` | Allow a `PYPILOT_ENGINE_VERSION` release that has no `SHA256SUMS` |
| `PYPILOT_DOWNLOAD_TIMEOUT=<seconds>` | Network timeout for downloads (default 60) |
| `HTTPS_PROXY`, `NO_PROXY` | Proxy for downloads, and hosts that bypass it |

Each GitHub release of `pypilot-cli` also carries a CycloneDX SBOM (`pypilot-cli.cdx.json`) that lists the bundled engine archives with their hashes.

---

## 💙 Support the project

PyPilot is free and open source, built and maintained in spare time. If it helps you:

- ⭐ [Star it on GitHub](https://github.com/pypilot-dev/pypilot): it's the easiest way to show support.
- 🐛 [Report a bug or request a feature](https://github.com/pypilot-dev/pypilot/issues): reproducible environment problems are especially welcome.

---

## 📄 License

PyPilot is licensed under the **GNU Affero General Public License v3.0 (AGPL-3.0-or-later)**. See the [LICENSE](https://github.com/pypilot-dev/pypilot-pip/blob/master/LICENSE) file for the full license text.
