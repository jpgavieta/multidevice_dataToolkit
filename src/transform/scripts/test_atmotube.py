# src/transform/scripts/test_atmotube.py
"""
Debug script for the Atmotube parser + registry (transform/parse/atmotube_parser.py,transform/register/atmotube_registry.py). 
Feeds a real captured API pull (saved via extract/scripts/inspect_data.py --full) through parser.parse() DIRECTLY.

Not part of the pipeline.
Run manually after touching atmotube_parser.py or atmotube_registry.py.

USAGE:
python -m transform.scripts.test_atmotube atmotube_kol_01
python -m transform.scripts.test_atmotube atmotube_kol_01 --input path/to/other_full.json
"""

import argparse
import json
import sys
from pathlib import Path

from general.study_registry import load_devices
from transform.parse import atmotube_parser
from transform.register.atmotube_registry import ATMOTUBE_REGISTRY

DEFAULT_INPUT_DIR = Path("src/extract/config/secrets/atmotube")

BASE_KEYS = {"device_id", "recorded_at", "latitude", "longitude"}
REQUIRED_READING_KEYS = BASE_KEYS | {standard_name for standard_name, *_ in ATMOTUBE_REGISTRY.values()}


def _load_raw(device_id: str, input_path: str | None) -> dict:
    path = Path(input_path) if input_path else DEFAULT_INPUT_DIR / f"{device_id}_full.json"
    if not path.exists():
        sys.exit(
            f"❌ No raw JSON found at {path}. Generate one with:\n"
            f"   python -m extract.scripts.inspect_data {device_id} --full"
        )
    return json.loads(path.read_text())


def _get_timezone(device_id: str) -> str | None:
    devices = {d["id"]: d for d in load_devices()}
    device = devices.get(device_id)
    if device is None:
        sys.exit(f"❌ '{device_id}' not found in config/devices.yml")
    tz = device.get("timezone")
    if not tz:
        print(f"  ⚠️ '{device_id}' has no 'timezone' in devices.yml — fine as long as every 'date' "
            f"value in the capture already carries a UTC offset.")
    return tz


def main():
    ap = argparse.ArgumentParser(description="Debug/test the atmotube parser against a real captured API pull.")
    ap.add_argument("device_id")
    ap.add_argument("--input", default=None, help="Path to a *_full.json capture (default: config/secrets/atmotube/<device_id>_full.json)")
    args = ap.parse_args()

    raw_data = _load_raw(args.device_id, args.input)
    timezone = _get_timezone(args.device_id)

    print(f"\nParsing {args.device_id} (tz={timezone})...")
    result = atmotube_parser.parse(raw_data, args.device_id, timezone)

    assert isinstance(result, dict), f"parse() should return a dict, got {type(result)}"
    assert "readings" in result, "parse() should always return a 'readings' key (even if empty list)"

    rows = result["readings"]
    assert isinstance(rows, list), f"'readings' should be a list, got {type(rows)}"
    if not rows:
        print("  ⚠️ 'readings' is empty — capture had no merged_data records to parse.")
        return

    for i, row in enumerate(rows):
        missing = REQUIRED_READING_KEYS - row.keys()
        assert not missing, f"readings[{i}] missing keys: {missing}"
        extra = row.keys() - REQUIRED_READING_KEYS
        assert not extra, f"readings[{i}] has unexpected keys: {extra} — registry/schema drift?"
        assert row["recorded_at"] is not None, f"readings[{i}] has no recorded_at — check 'date' field in capture"
        assert row["device_id"] == args.device_id, f"readings[{i}] device_id mismatch"

    # Duplicate timestamp check — mirrors inspect_data.py's chunk/cursor-boundary warning
    recorded_ats = [r["recorded_at"] for r in rows]
    dupes = len(recorded_ats) - len(set(recorded_ats))
    if dupes:
        print(f"  ⚠️ {dupes} duplicate recorded_at value(s) — check chunk/cursor-page boundary logic upstream.")

    print(f"  ✅ readings: {len(rows)} row(s), keys OK")
    print(f"\n✅ {args.device_id}: parser output looks structurally correct.")


if __name__ == "__main__":
    main()