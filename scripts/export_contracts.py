"""Export current OpenAPI and JSON schemas; no running database is needed."""

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rednexus.platform.api import create_app
from rednexus.platform.contracts import CapabilitySpec, RunInput, EventInput, MemoryInput

out = Path("contracts")
out.mkdir(exist_ok=True)
(out / "openapi.json").write_text(json.dumps(create_app().openapi(), indent=2) + "\n")
for model in [CapabilitySpec, RunInput, EventInput, MemoryInput]:
    (out / (model.__name__ + ".schema.json")).write_text(json.dumps(model.model_json_schema(), indent=2) + "\n")
print(f"Exported 5 contracts to {out}")
