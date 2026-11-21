"""Verify the independently written engineering cases used by public CI."""

import hashlib
import json
from pathlib import Path


def verify(folder=None):
    folder = folder or Path(__file__).parent / "fixtures" / "publication"
    manifest = json.loads((folder / "cases.json").read_text(encoding="utf-8"))
    if manifest["usage"] != "ENGINEERING_TEST_ONLY":
        raise ValueError("Unexpected fixture usage")
    cases = manifest["cases"]
    names = [case["file"] for case in cases]
    if len(names) < 6 or len(set(names)) != len(names):
        raise ValueError("Missing or duplicate fixture cases")
    if set(names) != {path.name for path in folder.glob("*.txt")}:
        raise ValueError("Fixture inventory differs from manifest")
    for case in cases:
        name = case["file"]
        if Path(name).name != name or not name.endswith(".txt"):
            raise ValueError("Invalid fixture filename")
        raw = (folder / name).read_bytes()
        if hashlib.sha256(raw).hexdigest() != case["sha256"]:
            raise ValueError(f"Fixture hash mismatch: {name}")
        raw.decode("utf-8")
    return len(cases)


if __name__ == "__main__":
    print(f"Verified {verify()} independently authored engineering fixtures")
