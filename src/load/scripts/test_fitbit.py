"""
Debug script for the transform -> load wiring for Fitbit devices. Runs a real captured pull (from extract/scripts/inspect_data.py --full) through:
    fitbit_parser.parse() -> load.load_raw_data() -> load.load_processed_data(),
against a REAL Postgres instance, then reads rows back to confirm they landed.

DESTRUCTIVE: inserts real rows into raw.ingests, fitbit.readings, fitbit.sleep_sessions, fitbit.sleep_stages, fitbit.exercise_sessions for the given device_id. 
Point this at a throwaway/test DB — see scripts/test_db.sh for a disposable ephemeral Postgres. 
Refuses to run against anything that doesn't look like localhost/a "test" DB unless overridden.

Not part of the pipeline. 
Run manually after touching load.py, or aftertransform.scripts.test_fitbit passes and you want to confirm the parser's
output actually lands correctly in Postgres.

USAGE:
PYTHONPATH=src ./src/load/scripts/test_db.sh python -m load.scripts.test_fitbit fitbit_kol_01
"""

import argparse
import json
import os
import sys
from pathlib import Path

from general.study_registry import load_devices
from transform.parse import fitbit_parser
from load.load import load_raw_data, load_processed_data, _get_connection, DESTINATION_TABLES, SLEEP_STAGES_TABLE

DEFAULT_INPUT_DIR = Path("src/extract/config/secrets/fitbit")


def _load_raw(device_id: str, input_path: str | None) -> dict:
    path = Path(input_path) if input_path else DEFAULT_INPUT_DIR / f"{device_id}_full.json"
    if not path.exists():
        sys.exit(
            f"❌ No raw JSON found at {path}. Generate one with:\n"
            f"   python -m extract.scripts.inspect_data {device_id} --full"
        )
    return json.loads(path.read_text())


def _get_timezone(device_id: str) -> str:
    devices = {d["id"]: d for d in load_devices()}
    device = devices.get(device_id)
    if device is None:
        sys.exit(f"❌ '{device_id}' not found in config/devices.yml")
    tz = device.get("timezone")
    if not tz:
        sys.exit(f"❌ '{device_id}' has no 'timezone' set — required for daily-grain fields.")
    return tz


def _confirm_safe_db():
    """Refuse to run against anything that doesn't look like a disposable test DB."""
    host = os.environ.get("DB_HOST", "")
    name = os.environ.get("DB_NAME", "")
    if "test" not in name.lower() and host not in ("localhost", "127.0.0.1"):
        sys.exit(
            f"❌ Refusing to run: DB_HOST={host!r} DB_NAME={name!r} doesn't look like a "
            f"local/test database. This script inserts real rows. Use scripts/test_db.sh, "
            f"or pass --i-know-this-is-destructive if you're sure."
        )


def main():
    ap = argparse.ArgumentParser(description="Test transform->load wiring for a fitbit device against a real (test) DB.")
    ap.add_argument("device_id")
    ap.add_argument("--input", default=None, help="Path to a *_full.json capture")
    ap.add_argument("--i-know-this-is-destructive", action="store_true", help="Skip the safe-DB heuristic check")
    args = ap.parse_args()

    if not args.i_know_this_is_destructive:
        _confirm_safe_db()

    raw_data = _load_raw(args.device_id, args.input)
    timezone = _get_timezone(args.device_id)

    print(f"\n[1/4] Parsing {args.device_id} (tz={timezone})...")
    parsed = fitbit_parser.parse(raw_data, args.device_id, timezone)
    expected_counts = {
        table: (1 if table == "profile" else len(rows))
        for table, rows in parsed.items()
    }
    print(f"   Parsed tables: {expected_counts}")

    print(f"\n[2/4] Loading raw payload into raw.ingests...")
    all_data = {"fitbit": {args.device_id: {"payload": raw_data, "ingest_method": "test_script"}}}
    ingest_ids, pulled_at = load_raw_data(all_data)
    assert ("fitbit", args.device_id) in ingest_ids, "load_raw_data() did not return an ingest_id for this device"
    print(f"   ✅ ingest_id = {ingest_ids[('fitbit', args.device_id)]}")

    print(f"\n[3/4] Loading processed data...")
    transformed = {"fitbit": {args.device_id: {"data": parsed}}}
    load_processed_data(transformed, ingest_ids, pulled_at) # doesn't raise on device-level failure, by design — see [4/4]

    print(f"\n[4/4] Verifying pipeline_runs + row counts...")
    conn = _get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT status, error_message FROM study.pipeline_runs "
                "WHERE device_type = 'fitbit' AND device_id = %s ORDER BY id DESC LIMIT 1",
                (args.device_id,),
            )
            row = cur.fetchone()
            assert row is not None, "No study.pipeline_runs row was logged for this device"
            status, error_message = row
            assert status == "success", f"pipeline_runs logged status={status!r}, error={error_message!r}"
            print(f"   ✅ pipeline_runs: status=success")

            for table_name, expected_count in expected_counts.items():
                if table_name == "sleep_stages":
                    sql_table = SLEEP_STAGES_TABLE
                    where_clause = "session_id IN (SELECT id FROM fitbit.sleep_sessions WHERE device_id = %s)"
                else:
                    key = ("fitbit", table_name)
                    if key not in DESTINATION_TABLES:
                        print(f"   ⚠️ No destination table registered for {key} — load.py silently skips these rows.")
                        continue
                    sql_table, _ = DESTINATION_TABLES[key]
                    where_clause = "device_id = %s"

                cur.execute(f"SELECT COUNT(*) FROM {sql_table} WHERE {where_clause}", (args.device_id,))
                if (result := cur.fetchone()) is not None:
                    actual_count = result[0]
                else:
                    actual_count = 0

                if actual_count == expected_count:
                    print(f"   ✅ {sql_table}: {actual_count} row(s) (matches parser output)")
                elif actual_count < expected_count:
                    print(f"   ⚠️ {sql_table}: expected {expected_count}, found {actual_count} — check for "
                        f"skipped rows (e.g. unresolved sleep_stage session_id, duplicate UNIQUE-key collisions).")
                else:
                    print(f"   ⚠️ {sql_table}: found MORE rows ({actual_count}) than parsed ({expected_count}) — "
                        f"likely pre-existing data from a prior run against this DB.")

            # activity-level (categorical) rows: confirm where the state value actually landed,
            # per the value_text/tag question flagged above.
            cur.execute(
                "SELECT tag, value_text FROM fitbit.readings "
                "WHERE device_id = %s AND data_type = 'activity-level' LIMIT 1",
                (args.device_id,),
            )
            sample = cur.fetchone()
            if sample:
                tag_val, value_text_val = sample
                print(f"   ℹ️ activity-level sample: tag={tag_val!r}, value_text={value_text_val!r} "
                      f"(module docstring says state should be in value_text — confirm this is intended)")
    finally:
        conn.close()

    print(f"\n✅ {args.device_id}: transform -> load wiring test complete.")


if __name__ == "__main__":
    main()