"""Build source-only ZIP and per-file checksums; excludes credentials/runtime data.

Run from the release root: python scripts/package_release.py /absolute/output.zip
Only known source directories/root files are eligible. Symlinks are rejected.
"""
import hashlib
from pathlib import Path
import sys
import zipfile

root = Path(__file__).resolve().parents[1]
destination = Path(sys.argv[1]).resolve()
allowed_dirs = {"rednexus", "tests", "docs", "examples", "contracts", "config", "scripts", ".github"}
allowed_root = {"README.md", "START_HERE_FA.md", "CHANGELOG.md", "pyproject.toml", "Dockerfile", "compose.yaml",
                ".gitignore", ".dockerignore", ".env.example", "requirements.txt", "requirements-dev.txt",
                "requirements-integration.txt", "requirements-browser.txt", "BOOTSTRAP.ps1", "SETUP.ps1",
                "START.ps1", "WORKER.ps1", "ECOSYSTEM.ps1", "VALIDATE.ps1", "START_ECOSYSTEM.cmd"}
excluded = {"__pycache__", ".pytest_cache", ".ruff_cache", ".venv", "data", "backups", "secrets", "node_modules"}
files = []
for path in sorted(root.rglob("*")):
    rel = path.relative_to(root)
    if any(part in excluded for part in rel.parts):
        continue
    if path.is_symlink():
        raise RuntimeError(f"refusing symlink: {rel}")
    if not path.is_file():
        continue
    if len(rel.parts) == 1 and path.name not in allowed_root:
        continue
    if len(rel.parts) > 1 and rel.parts[0] not in allowed_dirs:
        continue
    if path.name == ".env" or (path.name.startswith(".env.") and path.name != ".env.example"):
        continue
    if path.name.startswith("credentials") and path.suffix == ".json":
        continue
    if path.suffix in {".db", ".sqlite", ".sqlite3", ".pyc", ".log", ".zip"} or ".db-" in path.name:
        continue
    files.append(path)
manifest = "".join(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(root).as_posix()}\n" for p in files)
(root / "PACKAGE_MANIFEST.sha256").write_text(manifest, encoding="utf-8")
files.append(root / "PACKAGE_MANIFEST.sha256")
destination.parent.mkdir(parents=True, exist_ok=True)
with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
    for path in files:
        archive.write(path, "rednexus-ai/" + path.relative_to(root).as_posix())
with zipfile.ZipFile(destination) as archive:
    assert archive.testzip() is None
    for line in manifest.splitlines():
        expected, relative = line.split("  ", 1)
        assert hashlib.sha256(archive.read("rednexus-ai/" + relative)).hexdigest() == expected
print(f"{destination.name}: {len(files)} files; {destination.stat().st_size} bytes")
print("SHA256 " + hashlib.sha256(destination.read_bytes()).hexdigest())
