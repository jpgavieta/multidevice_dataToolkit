"""
Debug script for the transform -> load wiring for Atmotube devices. Same
pattern as test_fitbit_load.py — see that file's docstring for details.

USAGE:
    ./scripts/test_db.sh python -m load.scripts.test_atmotube_load atmotube_kol_01
"""

import argparse
import json
import os
import sys
from pathlib import Path

from general.study_registry import load_devices
from transform.parse import atmotube_parser
from load.load import load_raw_data, load_processed_data, _get_connection, DESTINATION_TABLES

DEFAULT_INPUT_DIR = Path("src/extract/config/secrets/atmotube")


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
    return device.get("timezone")  # atmotube tolerates None if 'date' already carries a UTC offset


def _confirm_safe_db():
    host = os.environ.get("DB_HOST", "")
    name = os.environ.get("DB_NAME", "")
    if "test" not in name.lower() and host not in ("localhost", "127.0.0.1"):
        sys.exit(
            f"❌ Refusing to run: DB_HOST={host!r} DB_NAME={name!r} doesn't look like a "
            f"local/test database. Use scripts/test_db.sh, or pass --i-know-this-is-destructive."
        )


def main():
    ap = argparse.ArgumentParser(description="Test transform->load wiring for an atmotube device against a real (test) DB.")
    ap.add_argument("device_id")
    ap.add_argument("--input", default=None)
    ap.add_argument("--i-know-this-is-destructive", action="store_true")
    args = ap.parse_args()

    if not args.i_know_this_is_destructive:
        _confirm_safe_db()

    raw_data = _load_raw(args.device_id, args.input)
    timezone = _get_timezone(args.device_id)

    print(f"\n[1/4] Parsing {args.device_id} (tz={timezone})...")
    parsed = atmotube_parser.parse(raw_data, args.device_id, timezone)
    expected_count = len(parsed.get("readings", []))
    print(f"   Parsed readings: {expected_count}")

    print(f"\n[2/4] Loading raw payload into raw.ingests...")
    all_data = {"atmotube": {args.device_id: {"payload": raw_data, "ingest_method": "test_script"}}}
    ingest_ids, pulled_at = load_raw_data(all_data)
    ingest_id = ingest_ids.get(("atmotube", args.device_id))
    assert ingest_id is not None, "load_raw_data() did not return an ingest_id for this device"
    print(f"   ✅ ingest_id = {ingest_id}")

    print(f"\n[3/4] Loading processed data...")
    transformed = {"atmotube": {args.device_id: {"data": parsed}}}
    load_processed_data(transformed, ingest_ids, pulled_at)

    print(f"\n[4/4] Verifying pipeline_runs + row count...")
    conn = _get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT status, error_message FROM study.pipeline_runs "
                "WHERE device_type = 'atmotube' AND device_id = %s ORDER BY id DESC LIMIT 1",
                (args.device_id,),
            )
            row = cur.fetchone()
            assert row is not None, "No study.pipeline_runs row was logged for this device"
            status, error_message = row
            assert status == "success", f"pipeline_runs logged status={status!r}, error={error_message!r}"
            print(f"   ✅ pipeline_runs: status=success")

            # ↓↓↓ THIS is the chunk that replaces your current lines 94-114 ↓↓↓
            sql_table, _ = DESTINATION_TABLES[("atmotube", "readings")]
            cur.execute(f"SELECT COUNT(*) FROM {sql_table} WHERE device_id = %s", (args.device_id,))
            if (result := cur.fetchone()) is not None:
                actual_count = result[0]
            else:
                actual_count = 0

            if actual_count == expected_count:
                print(f"   ✅ {sql_table}: {actual_count} row(s) (matches parser output)")
            else:
                print(f"   ⚠️ {sql_table}: expected {expected_count}, found {actual_count} — check for "
                    f"duplicate recorded_at values colliding on upsert, or pre-existing data in this DB.")

            cur.execute(
                f"SELECT COUNT(*) FROM {sql_table} WHERE device_id = %s AND location IS NOT NULL",
                (args.device_id,),
            )
            if (result := cur.fetchone()) is not None:
                geo_count = result[0]
            else:
                geo_count = 0
            print(f"   ℹ️ {geo_count}/{actual_count} row(s) have a non-NULL location (GPS fix present)")
            # ↑↑↑ end of replacement chunk ↑↑↑
    finally:
        conn.close()

    print(f"\n✅ {args.device_id}: transform -> load wiring test complete.")


if __name__ == "__main__":
    main()