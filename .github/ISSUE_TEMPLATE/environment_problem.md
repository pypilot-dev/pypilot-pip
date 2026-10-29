---
name: Environment problem
about: PyPilot ran, but got your Python environment, packages or GPU setup wrong
title: ""
labels: environment
assignees: ""
---

**What happened**
What PyPilot reported or did, and what you expected instead.

**`pypilot --version`**
Both lines, please: the engine (`pypilot X.Y.Z`) and the wrapper (`pypilot-cli X.Y.Z (engine: ...)`), plus any `warning:` lines.

```
paste here
```

**`pypilot doctor --json`**
Run it in the project folder. It lists your interpreter, virtual environment, manifests and GPU/CUDA facts; remove anything you consider private before posting.

```json
paste here
```

**Install method**
pip / pipx / `uv tool` / platform wheel or pure wheel (`pip show -f pypilot-cli` lists `pypilot/_engine/` if the engine is bundled).

**Anything else**
Proxy or offline setup (`PYPILOT_OFFLINE`, `HTTPS_PROXY`), `PYPILOT_ENGINE_VERSION`, or a `pypilot` engine on PATH or in `~/.cargo/bin`.
