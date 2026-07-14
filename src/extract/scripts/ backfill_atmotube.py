# src/extract/scripts/backfill_atmotube.py
"""
One-time backfill: converts Atmotube app-exported CSVs (May–June history, predating API/cloud pairing) into the same shape atmotube_client.py's
extract_raw_data() produces from the live API — so transform/parsers/ atmotube.py only ever has to handle ONE input shape, regardless of source.

Reads every *.csv in extract/config/secrets/atmotube/backfill/ (gitignored, not tracked — these are real participant data)

Filename convention (as exported by the Atmotube app):
    <MAC>_<start date DD-Mon-YYYY>_<end date DD-Mon-YYYY>.csv
    e.g. C3CBE16AE294_01-May-2026_12-Jun-2026.csv

One device can have multiple CSV files (multiple export windows) — these are combined into one continuous record set per MAC.

Fields the CSV export does NOT include (legitimately null, not a bug):
    pm05_num, pm1_num, pm10_num, pm25_num, pm_size,
    satellites_fixed, satellites_in_view, snr0_19, snr20_49, snr50_99, snr_avg

USAGE:
python -m extract.scripts.backfill_atmotube                 # all devices found
python -m extract.scripts.backfill_atmotube --device atmotube_kol_01
python -m extract.scripts.backfill_atmotube --dry-run        # no output file
"""

import argparse
import json
import re
from pathlib import Path
from datetime import timedelta

import pandas as pd

from general.device_registry import load_devices

BACKFILL_DIR = Path(__file__).resolve().parents[1] / "config" / "secrets" / "atmotube" / "backfill"

FILENAME_RE = re.compile(r"^([A-Fa-f0-9]{12})_.*\.csv$")

KOLKATA_UTC_OFFSET = timedelta(hours=5, minutes=30)

# CSV column name -> API MeasurementItem field name.
# Matched by header NAME, not position, in case some device exports differ slightly (firmware version, app version, etc.) — do not assume column order.
COLUMN_MAP = {
    "AQS": "aqs",
    "PM1.0 (µg/m³)": "pm1",
    "PM2.5 (µg/m³)": "pm25",
    "PM10 (µg/m³)": "pm10",
    "Temperature (°C)": "t",
    "Humidity (%)": "h",
    "Pressure (hPa)": "p",
    "TVOC Index": "voc_index",
    "TVOC (ppm)": "voc",
    "NOx Index": "nox_index",
    "CO2 (ppm)": "co2",
    "Latitude": "lat",
    "Longitude": "lon",
    "Altitude (m)": "altitude",
    "Position Error (m)": "position_error",
    "Battery (%)": "battery",
}

# Fields the API schema has that this CSV export never provides — always null.
ALWAYS_NULL_FIELDS = [
    "pm05_num", "pm1_num", "pm10_num", "pm25_num", "pm_size",
    "satellites_fixed", "satellites_in_view",
    "snr0_19", "snr20_49", "snr50_99", "snr_avg",
]


def _find_date_column(df: pd.DataFrame) -> str:
    """The date column header embeds a UTC offset, e.g. 'Date (UTC+05:30)' —
    match by prefix rather than hardcoding the exact offset string, in case
    a device's export was generated under a different configured timezone."""
    for col in df.columns:
        if col.strip().startswith("Date (UTC"):
            return col
    raise ValueError(f"No 'Date (UTC...)' column found. Columns present: {list(df.columns)}")


def _map_charging(value) -> tuple:
    """Returns (charging: bool, recently_charged: bool)."""
    v = str(value).strip().lower()
    if v == "yes":
        return True, False
    if v == "cd":
        return False, True
    return False, False  # "no", blank, or unrecognized


def _row_to_measurement(row: pd.Series, date_col: str) -> dict:
    # Local Kolkata time (naive) -> shift to UTC to match the live API's convention
    local_dt = pd.to_datetime(row[date_col])
    utc_dt = local_dt - KOLKATA_UTC_OFFSET

    charging, recently_charged = _map_charging(row.get("Charging"))

    record = {
        "date": utc_dt.strftime("%Y-%m-%dT%H:%M:%S"),
        "charging": charging,
        "recently_charged": recently_charged,
        "motion": str(row.get("Motion", "")).strip().lower() == "yes",
    }

    for csv_col, api_field in COLUMN_MAP.items():
        val = row.get(csv_col)
        record[api_field] = None if pd.isna(val) else val

    for field in ALWAYS_NULL_FIELDS:
        record[field] = None

    return record


def _load_one_csv(path: Path) -> pd.DataFrame:
    # utf-8-sig handles the BOM at the start of the header row
    # (seen as "\ufeffDate (UTC+05:30)" in the raw file)
    return pd.read_csv(path, encoding="utf-8-sig")


def _group_files_by_mac() -> dict:
    """Returns {mac: [file_paths]} for every CSV in BACKFILL_DIR."""
    if not BACKFILL_DIR.exists():
        raise FileNotFoundError(f"Backfill directory not found: {BACKFILL_DIR}")

    groups: dict = {}
    for path in sorted(BACKFILL_DIR.glob("*.csv")):
        m = FILENAME_RE.match(path.name)
        if not m:
            print(f"  ⚠️ Skipping '{path.name}' — doesn't match <MAC>_<...>.csv convention")
            continue
        mac = m.group(1).upper()
        groups.setdefault(mac, []).append(path)
    return groups


def _mac_to_device_id_map() -> dict:
    devices = load_devices()
    result = {}
    for d in devices:
        if d.get("type") != "atmotube":
            continue
        mac = d["mac"].replace(":", "").replace("-", "").upper()
        result[mac] = d["id"]
    return result


def process_device(mac: str, files: list, mac_to_device: dict) -> dict:
    device_id = mac_to_device.get(mac, f"UNKNOWN_DEVICE(mac={mac})")
    print(f"\n--- {device_id} (mac={mac}) ---")
    print(f"  Files: {[f.name for f in files]}")

    all_records = []
    for path in files:
        df = _load_one_csv(path)
        date_col = _find_date_column(df)
        for _, row in df.iterrows():
            all_records.append(_row_to_measurement(row, date_col))

    all_records.sort(key=lambda r: r["date"])

    # Duplicate check across combined files, same category of check used
    # elsewhere in this pipeline for live-API pagination
    dates = [r["date"] for r in all_records]
    dupes = len(dates) - len(set(dates))
    if dupes:
        print(  f"  ⚠️ {dupes} duplicate timestamp(s) across combined files — "
                f"check for overlapping export date ranges")

    print(f"  Total records: {len(all_records)}")
    if all_records:
        print(f"  Range: {all_records[0]['date']} .. {all_records[-1]['date']}  (UTC)")

    return {
        "mac": mac,
        "device_id": device_id,
        "merged_data": all_records,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--device", default=None, help="Only process this device_id")
    parser.add_argument("--dry-run", action="store_true", help="Parse and report only, write nothing")
    parser.add_argument("--out", default=None, help="Output path for JSON (default: prints summary only)")
    args = parser.parse_args()

    mac_to_device = _mac_to_device_id_map()
    device_to_mac = {v: k for k, v in mac_to_device.items()}

    groups = _group_files_by_mac()
    if not groups:
        print(f"No CSVs found in {BACKFILL_DIR}")
        return

    if args.device:
        target_mac = device_to_mac.get(args.device)
        if not target_mac:
            print(f"❌ '{args.device}' not found in devices.yml as an atmotube device")
            return
        groups = {target_mac: groups[target_mac]} if target_mac in groups else {}
        if not groups:
            print(f"❌ No CSV files found for mac={target_mac} ('{args.device}')")
            return

    results = {}
    for mac, files in groups.items():
        results[mac] = process_device(mac, files, mac_to_device)

    if args.dry_run:
        print("\n--dry-run set: no output written.")
        return

    if args.out:
        out_path = Path(args.out)
        out_path.write_text(json.dumps(results, indent=2))
        print(f"\n✅ Wrote {out_path}")
    else:
        print(  "\nNo --out path given — results computed but not written. "
                "Pass --out <path.json> to save, or import process_device()/"
                "main() logic directly into your load step.")


if __name__ == "__main__":
    main()