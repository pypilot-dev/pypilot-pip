"""
Complete uv's CycloneDX export with the engine the platform wheels bundle.

    uv export --frozen --no-dev --format cyclonedx1.5 --preview-features sbom-export -o uv-sbom.json
    python scripts/sbom.py uv-sbom.json pypilot-cli.cdx.json

uv lists the Python dependencies (none at runtime). The native engine is not a
Python package, so it is added here: one component per pinned release asset,
with the SHA-256 from `ENGINE_SHA256` and the URL it comes from.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from pypilot import __version__, binary, engine  # noqa: E402


def engine_components() -> List[Dict[str, Any]]:
    version = binary.DEFAULT_TAG.lstrip("v")
    components = []
    for asset, digest in sorted(binary.ENGINE_SHA256.items()):
        components.append(
            {
                "type": "application",
                "bom-ref": f"pypilot-engine:{asset}",
                "name": "pypilot",
                "version": version,
                "description": f"PyPilot native engine, release asset {asset}",
                "licenses": [{"license": {"id": "AGPL-3.0-or-later"}}],
                "hashes": [{"alg": "SHA-256", "content": digest}],
                "purl": f"pkg:github/{binary.GITHUB_REPO}@{binary.DEFAULT_TAG}",
                "externalReferences": [
                    {"type": "distribution", "url": engine.release_url(binary.DEFAULT_TAG, asset)},
                    {"type": "vcs", "url": f"https://github.com/{binary.GITHUB_REPO}"},
                ],
            }
        )
    return components


def main(src: str, dest: str) -> None:
    bom: Dict[str, Any] = json.loads(Path(src).read_text(encoding="utf-8"))
    project = bom["metadata"]["component"]
    if project.get("name") != "pypilot-cli" or project.get("version") != __version__:
        sys.exit(f"{src} describes {project.get('name')} {project.get('version')}, not pypilot-cli {__version__}")
    project["purl"] = f"pkg:pypi/pypilot-cli@{__version__}"
    project.setdefault("licenses", [{"license": {"id": "AGPL-3.0-or-later"}}])

    added = engine_components()
    bom.setdefault("components", []).extend(added)
    deps = bom.setdefault("dependencies", [])
    root = next((d for d in deps if d.get("ref") == project["bom-ref"]), None)
    if root is None:
        root = {"ref": project["bom-ref"]}
        deps.append(root)
    root.setdefault("dependsOn", []).extend(c["bom-ref"] for c in added)
    deps.extend({"ref": c["bom-ref"]} for c in added)

    Path(dest).parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "w", encoding="utf-8", newline="\n") as f:
        json.dump(bom, f, indent=2)
        f.write("\n")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
