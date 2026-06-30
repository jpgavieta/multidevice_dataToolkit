import os
import csv
import pandas as pd
import errno
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

# This should stay device-agnostic: reads files now, will fetch from APIs later.
# Logic is based on device_type (top-level folder), device_id (filename) underneath.

# ============================================================================================================

def _expected_col_count(file_path: str) -> int:
    """Reads just the header row to determine the expected number of columns."""
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        header_line = f.readline()
    return len(next(csv.reader([header_line])))


def _make_bad_line_fixer(expected_cols: int):
    """
    Returns a closure for pandas' on_bad_lines: if a row has more fields
    than the header, merge the overflow back into the last column.
    """
    def fix_bad_line(bad_line):
        if len(bad_line) > expected_cols:
            correct_part = bad_line[: expected_cols - 1]
            merged_last = ",".join(bad_line[expected_cols - 1:])
            correct_part.append(merged_last)
            return correct_part
        return bad_line
    return fix_bad_line


def _load_one_file(file_path: str, file_name: str):
    """Loads a single CSV file. Returns (device_id, df) or (device_id, None) on failure."""
    device_id = os.path.splitext(file_name)[0]
    try:
        expected_cols = _expected_col_count(file_path)
        fix_bad_line = _make_bad_line_fixer(expected_cols)

        df = pd.read_csv(
            file_path,
            engine="python",
            on_bad_lines=fix_bad_line,
            skipinitialspace=True,
        )
        return device_id, df, None
    except Exception as e:
        return device_id, None, e


def extract_raw_data(mount_path: str, max_workers: int = 8) -> dict[str, dict[str, pd.DataFrame]]:
    """
    Scans device_type folders under mount_path and loads each CSV as its
    own raw DataFrame, keyed by device_id (filename without extension).

    Each device_id is kept SEPARATE on purpose — device-type parsers expect
    to run on one device_id's file at a time. Files within (and across)
    device_type folders are loaded concurrently via a thread pool, since
    this is I/O-bound work.

    Parameters
    ----------
    mount_path : str
        Root folder containing one subfolder per device_type
        (e.g. "Atmotube", "Ponyopi", "Fitbit").
    max_workers : int
        Number of threads to use for concurrent file loading. Tune based
        on disk type (higher for SSD/network mounts, lower for spinning disks).

    Returns
    -------
    dict
        { device_type: { device_id: raw_df } }
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

    # Build a flat list of (device_type, file_path, file_name) across ALL folders
    # so we can parallelize across the whole tree, not just within one folder.
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
            file_path = os.path.join(folder_path, file_name)
            tasks.append((device_type, file_path, file_name))

    print(f"Found {len(tasks)} CSV file(s) across all device_type folders. Loading with {max_workers} threads...")

    # Submit all tasks, track which device_type each future belongs to
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

    # Summary per device_type
    for device_type in list(all_data.keys()):
        print(f"  ✅ {device_type}: {len(all_data[device_type])} device_id(s) loaded")

    # Mention folders that had no valid CSVs (need to recheck since we flattened)
    scanned_types = {dt for dt, _, _ in tasks}
    for device_type in scanned_types - all_data.keys():
        print(f"  ⚠️ {device_type}: No valid CSVs loaded")

    return all_data

# Example: data = extract_raw_data("/home/yul/mnt/proton-data")
#          data.keys()                                                    # dict_keys(['Atmotube', 'Ponyopi', 'Fitbit'])
#          data["Atmotube"].keys()                                        # dict_keys(['C3CBE16AE294_01-May-2026_12-Jun-2026', ...])
#          data["Atmotube"]["C3CBE16AE294_01-May-2026_12-Jun-2026"]       # raw DataFrame for that device_id


if __name__ == "__main__":
    MOUNT_PATH = "/home/yul/mnt/proton-data"
    data = extract_raw_data(MOUNT_PATH, max_workers=8)
    if data:
        print(f"\n🚀 Success! Loaded {len(data)} device_type folder(s).")
        for device_type, files in data.items():
            print(f"   {device_type}: {list(files.keys())}")