import io
import os
import csv
import pandas as pd
import errno
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

# This should stay device-agnostic: reads files now, will fetch from APIs later.
# Logic is based on device_type (top-level folder), device_id (filename) underneath.

# ============================================================================================================

def _fix_bad_lines(raw_bytes: bytes) -> io.BytesIO:
    """
    Read raw CSV bytes, detect the expected column count from the header,
    and merge any overflow fields on bad rows back into the last column —
    same logic as before, but done once on the raw text before pandas
    touches it, so we can use engine="c" for the actual parse.
    """
    text = raw_bytes.decode("utf-8", errors="ignore")
    reader = csv.reader(text.splitlines())
    rows = list(reader)

    if not rows:
        return io.BytesIO(raw_bytes)

    expected_cols = len(rows[0])
    fixed_rows = []
    for row in rows:
        if len(row) > expected_cols:
            merged = row[:expected_cols - 1] + [",".join(row[expected_cols - 1:])]
            fixed_rows.append(merged)
        else:
            fixed_rows.append(row)

    # Write fixed rows back out as a clean CSV in memory
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerows(fixed_rows)
    return io.BytesIO(buf.getvalue().encode("utf-8"))


def _load_one_file(file_path: str, file_name: str):
    """
    Loads a single CSV file. Returns (device_id, df, error).
    Reads the file exactly once — bad-line fixing and CSV parsing both
    work off the same in-memory bytes, so no second network round-trip.
    """
    device_id = os.path.splitext(file_name)[0]
    try:
        with open(file_path, "rb") as f:   # binary — let _fix_bad_lines handle encoding
            raw_bytes = f.read()

        buf = _fix_bad_lines(raw_bytes)

        df = pd.read_csv(
            buf,
            engine="c",                    # 2–5x faster than engine="python"
            skipinitialspace=True,
        )
        return device_id, df, None
    except Exception as e:
        return device_id, None, e


def extract_raw_data(
    mount_path: str,
    max_workers: int = 16              # bumped from 8 — I/O bound work scales well with more threads
) -> dict[str, dict[str, pd.DataFrame]]:
    """
    Scans device_type folders under mount_path and loads each CSV as its
    own raw DataFrame, keyed by device_id (filename without extension).
    """
    if not os.path.exists(mount_path):
        print(f"❌ Path not found: {mount_path}")
        return {}

    all_data: dict[str, dict[str, pd.DataFrame]] = {}
    print_lock = Lock()

    def safe_print(msg):
        with print_lock:
            print(msg)

    print(f"--- Scanning: {mount_path} ---")

    tasks = []
    for device_type in os.listdir(mount_path):
        folder_path = os.path.join(mount_path, device_type)
        if not os.path.isdir(folder_path):
            continue

        try:
            file_names = os.listdir(folder_path)
        except OSError as e:
            if e.errno == errno.EIO:
                print(f"  ❌ Skipping unreadable folder (EIO): {folder_path}")
                continue
            raise

        for file_name in file_names:
            if not file_name.endswith(".csv"):
                continue
            tasks.append((device_type, os.path.join(folder_path, file_name), file_name))

    print(f"Found {len(tasks)} CSV file(s). Loading with {max_workers} threads...")

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_task = {
            executor.submit(_load_one_file, file_path, file_name): (device_type, file_name)
            for device_type, file_path, file_name in tasks
        }

        for future in as_completed(future_to_task):
            device_type, file_name = future_to_task[future]
            device_id, df, error = future.result()

            if df is None:
                safe_print(f"   ❌ Failed {file_name}: {error}")
                continue

            all_data.setdefault(device_type, {})[device_id] = df
            safe_print(f"   ✅ Loaded {device_id}: {df.shape}  [{device_type}]")

    for device_type in list(all_data.keys()):
        print(f"  ✅ {device_type}: {len(all_data[device_type])} device_id(s) loaded")

    scanned_types = {dt for dt, _, _ in tasks}
    for device_type in scanned_types - all_data.keys():
        print(f"  ⚠️ {device_type}: No valid CSVs loaded")

    return all_data

# Example: data = extract_raw_data("/home/yul/mnt/proton-data")