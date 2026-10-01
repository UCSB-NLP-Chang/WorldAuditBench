"""Skip only external-image tests until the pending resource pack is restored."""
from pathlib import Path
import json
import pytest

ROOT = Path(__file__).resolve().parents[1]


def pytest_collection_modifyitems(items):
    pack = json.loads((ROOT / "resources/manifest.json").read_text())
    images = [r for r in pack["resources"]
              if r.get("path", "").startswith("examples/icl/images/")]
    missing = any(not (ROOT / r["path"]).is_file() for r in images)
    runtime_missing = not (ROOT / "out/native-agents/venv/bin/python").is_file()
    if missing or runtime_missing:
        mark = pytest.mark.skip(reason="ICL images pending Hugging Face release; restore pack and run native-agents/setup.py")
        for item in items:
            if "requires_icl" in item.keywords:
                item.add_marker(mark)
