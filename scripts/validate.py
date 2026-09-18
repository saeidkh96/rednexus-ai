"""Cross-platform local validation. Optional service tests clearly report skips."""

from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
commands = [
    ["-m", "ruff", "check", "rednexus", "tests"],
    ["-m", "pytest", "-q"],
    ["-m", "rednexus.platform.cli", "demo"],
    ["-m", "rednexus.demo"],
]
for command in commands:
    subprocess.run([sys.executable, *command], cwd=root, check=True)
print("Local validation passed. Run scripts/check_release.py for stable-release gates.")
