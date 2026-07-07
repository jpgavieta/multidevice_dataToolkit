import re
import pandas as pd

from typing import Any, Literal, Dict
from functools import reduce
from datetime import datetime

# ============================================================================================================
# Helpers for Df Navigation in notebooks/

def skim_loaded_data(data):
    """
    Displays a summary of all devices and dfs in the loaded pipeline data.

    Parameters
    ----------
    data : dict
        Output of load_pipeline(), structured as:
        { device_type: { device_id: { "data": { table_name: { "df": df, "cols": [...] } } } } }
        Every table — including "gis" and "all" — lives under "data" with no
        special-cased top-level keys.
    """
    for device_type, devices in data.items():
        for device_id, content in devices.items():
            dfs = list(content["data"].keys())
            print(f"{device_type}/{device_id}")
            print(f"  dfs : {dfs}")
            for t in dfs:
                df = content["data"][t]["df"]
                print(f"  {t:10s}: {df.shape}  |  {df['datetime'].min()} → {df['datetime'].max()}")
            print()

def skim(data, device_type=None, device_id=None, df_key=None, col=None):
    # a. no filtering: show everything
    if device_type is None:
        return skim_loaded_data(data)

    # one or more device_types
    if isinstance(device_type, (list, tuple, set)):
        for dt in device_type:
            if dt not in data:
                print(f"⚠️ {dt} is not available")
                continue
            skim(data, dt, device_id, df_key, col)
        return None

    if device_type not in data:
        print(f"⚠️ {device_type} is not available")
        return None

    # b. filter to one device_type (all its device_ids)
    if device_id is None:
        return skim_loaded_data({device_type: data[device_type]})

    # one or more device_ids
    if isinstance(device_id, (list, tuple, set)):
        for did in device_id:
            if did not in data[device_type]:
                print(f"⚠️ {did} is not available")
                continue
            skim(data, device_type, did, df_key, col)
        return None

    if device_id not in data[device_type]:
        print(f"⚠️ {device_id} is not available")
        return None

    # now we have one specific device_id
    content = data[device_type][device_id]

    # c. filter to one specific device_id (all its dfs)
    if df_key is None:
        return skim_loaded_data({device_type: {device_id: content}})

    # one or more df_keys
    if isinstance(df_key, (list, tuple, set)):
        for dk in df_key:
            if dk not in content["data"]:
                print(f"⚠️ {dk} is not available")
                continue
            skim(data, device_type, device_id, dk, col)
        return None

    if df_key not in content["data"]:
        print(f"⚠️ {df_key} is not available")
        return None

    df = content["data"][df_key]["df"]

    # d. filter to one df (df_key) -> per-column: name (len, dtype)
    if col is None:
        print(f"{device_type}/{device_id}/{df_key}")
        print(f"  df.shape: {df.shape}")
        if "datetime" in df.columns:
            print(f"  range   : {df['datetime'].min()} → {df['datetime'].max()}")
        for c in df.columns:
            s = df[c]
            print(f"  {c:25s}: ({len(s)}, {s.dtype})")
        return None

    # one or more cols
    if isinstance(col, (list, tuple, set)):
        for c in col:
            if c not in df.columns:
                print(f"⚠️ {c} is not available")
                continue
            skim(data, device_type, device_id, df_key, c)
        return None

    if col not in df.columns:
        print(f"⚠️ {col} is not available")
        return None

    # e. filter to one variable-only: one column/Series
    s = df[col]
    print(f"{device_type}/{device_id}/{df_key}/{col}")
    print(f"  ({len(s)}, {s.dtype})")
    if "datetime" in df.columns and col != "datetime":
        valid_dt = df.loc[s.notna(), "datetime"]
        if not valid_dt.empty:
            print(f"  range   : {valid_dt.min()} → {valid_dt.max()}  (where '{col}' is present)")
        else:
            print(f"  range   : no non-null values for '{col}'")
    return None

# Examples:
#   skim(data)                                                                   # all loaded data
#   skim(data, "Atmotube")                                                       # all Atmotube device_ids
#   skim(data, ["Atmotube", "Ponyopi"])                                          # all device_ids, both device types
#   skim(data, "Atmotube", device_id)                                            # one device_id, all its dfs
#   skim(data, "Atmotube", [device_a, device_b])                                 # two device_ids, all dfs each
#   skim(data, "Atmotube", device_id, "pm")                                      # one df
#   skim(data, "Atmotube", device_id, ["pm", "weather"])                         # two dfs, one device  
#   skim(data, "Atmotube", [device_a, device_b], "pm")                           # same df, two devices
#   skim(data, "Atmotube", device_id, "pm", "pm2_5_ugm3_atm")                    # one column
#   skim(data, "Atmotube", device_id, "pm", ["pm2_5_ugm3_atm", "pm10_ugm3_atm"]) # two columns


def unwrap(content: Any) -> Dict[str, pd.DataFrame]:
    """
    Unwraps ONE device's content (a nested dict) into a flat dict of {df_key: df} — the
    raw material merge() expects.

    Accepts:
    -   a device content dict (has a "data" key): unwraps content["data"],
        pulling just the "df" out of each {"df": df} entry.
    -   an already-flat {df_key: df} dict: returned unchanged, so calling
        unwrap() on something already extracted is always safe.
    """
    if isinstance(content, dict) and "data" in content:
        return {
            k: v["df"]
            for k, v in content["data"].items()
            if isinstance(v, dict) and "df" in v
        }
    return content

# Example:
#   unwrap(get(data, "device_type", "device_id"))      
#   OR
#   device = get(data, "device_type", "device_id")      
#   unwrap(device)                                    # equivalent — get() already returns this same shape


def merge(
    devices: dict[str, dict],
    df_names=None,
    how: Literal['left', 'right', 'outer', 'inner', 'cross', 'left_anti', 'right_anti'] = "outer",
):
    """
    Merge function for the unwrap() output (dict of {table_name: df}) into one
    wide DataFrame joined on "datetime".

    Args:
        devices: dict of {device_name: {table_name: df}}. Pass a single
            device with any key (e.g. {"": dfs}) if you don't need column
            suffixing; pass multiple devices to get columns suffixed with
            _<device_name>.
        df_names: str or list/tuple/set to select which tables to merge
        how: join type for pd.merge (default "outer")

    Raises:
        ValueError: if a requested df_name isn't found in a device's tables.
    """
    suffix_needed = len(devices) > 1
    all_tables = []
    for device_name, dfs in devices.items():
        if df_names:
            invalid = [n for n in df_names if n not in dfs]
            if invalid:
                label = f"'{device_name}'" if device_name else "the dict"
                raise ValueError(
                    f"df(s) not found in {label}: {invalid}. Available: {list(dfs.keys())}"
                )
            tables = [dfs[n] for n in df_names]
        else:
            tables = list(dfs.values())
        if suffix_needed:
            tables = [
                t.rename(columns={c: f"{c}_{device_name}" for c in t.columns if c != "datetime"})
                for t in tables
            ]
        all_tables.extend(tables)

    if not all_tables:
        return pd.DataFrame()

    return reduce(
        lambda left, right: pd.merge(left, right, on="datetime", how=how),
        all_tables
    )

# Example:
#   merge(unwrap(device))                                                          # one device, all tables, no suffix
#   merge(unwrap(device), df_names=["pm"])                                         # one device, just pm
#   merge(device_a=unwrap(content_a), device_b=unwrap(content_b))                  # two devices, all tables, suffixed
#   merge(device_a=unwrap(content_a), device_b=unwrap(content_b), df_names=["pm"]) # two devices, just pm, suffixed


def get(data, device_type=None, device_id=None, df_key=None, col=None):
    """
    The single navigation function for the nested pipeline structure.
    Always returns a dict or a Series — never a bare DataFrame at the top
    level.

    Unwrapping a table's {"df": df} entry into an actual DataFrame
    happens exclusively inside unwrap() — get() never reaches into ["df"]
    itself.

    Supports:
        - device_type: str or list/tuple/set
        - device_id: str or list/tuple/set
        - df_key: str or list/tuple/set
        - col: None, str, or list/tuple/set

    Raises:
        KeyError: if a SINGLE device_type/device_id/df_key/col is given
            and it isn't found.
    Note:
        When given as part of a list/tuple/set, a missing item is instead
        skipped with a warning, so one bad ID doesn't abort a batch lookup.
    """
    # a. if no given device_type
    if device_type is None:
        return unwrap(data)

    # one or more device_types
    if isinstance(device_type, (list, tuple, set)):
        out = {}
        for dt in device_type:
            if dt not in data:
                print(f"⚠️ device_type '{dt}' is not available")
                continue
            out[dt] = get(data, dt, device_id, df_key, col)
        return out

    if device_type not in data:
        raise KeyError(f"device_type '{device_type}' is not available")

    # b. if no given device_id, return all devices of the given type
    if device_id is None:
        return data[device_type]

    # helper: select column(s) from a DataFrame.
    #   col is None  -> df unchanged (still a DataFrame, but only ever as
    #                   a dict VALUE — never returned bare at top level)
    #   col is a str -> a Series
    #   col is a list/tuple/set -> dict {col_name: Series}, never a
    #                   sub-DataFrame
    def select_cols(df, table_name, did, dtypename):
        if col is None:
            return df

        if isinstance(col, (list, tuple, set)):
            # Always keep datetime, even if the caller didn't ask for it —
            # merge() needs it to join tables together.
            cols_to_use = list(col)
            if "datetime" in df.columns and "datetime" not in cols_to_use:
                cols_to_use = ["datetime"] + cols_to_use

            missing = [c for c in cols_to_use if c not in df.columns]
            for c in missing:
                print(
                    f"⚠️ col '{c}' is not available in df '{table_name}' "
                    f"(device_type '{dtypename}', device_id '{did}')"
                )

            valid_cols = [c for c in cols_to_use if c in df.columns]
            return df[valid_cols]  # DataFrame, not a dict of Series

        if col not in df.columns:
            raise KeyError(
                f"col '{col}' is not available in df '{table_name}' "
                f"(device_type '{dtypename}', device_id '{did}')"
            )

        return df[col]  # still a Series for a single column name — see note below

    # one or more device_ids
    if isinstance(device_id, (list, tuple, set)):
        out = {}
        for did in device_id:
            if did not in data[device_type]:
                print(
                    f"⚠️ device_id '{did}' is not available in device_type '{device_type}'"
                )
                continue
            out[did] = get(data, device_type, did, df_key, col)
        return out

    if device_id not in data[device_type]:
        raise KeyError(
            f"device_id '{device_id}' is not available in device_type '{device_type}'"
        )

    # c. single device_id — unwrap once via unwrap(), use it everywhere below
    content = data[device_type][device_id]
    dfs = unwrap(content)  # {table_name: df, ...} — the ONLY unwrap point

    # c1. if df_key is None: every table for this device
    if df_key is None:
        return {
            k: select_cols(df, k, device_id, device_type) for k, df in dfs.items()
        }

    # c2. df_key is a collection: just those tables, always as a dict
    if isinstance(df_key, (list, tuple, set)):
        out = {}
        for k in df_key:
            if k not in dfs:
                print(
                    f"⚠️ df '{k}' is not available in device_id '{device_id}' "
                    f"(device_type '{device_type}')"
                )
                continue
            out[k] = select_cols(dfs[k], k, device_id, device_type)
        return out

    if df_key not in dfs:
        raise KeyError(
            f"df '{df_key}' is not available in device_id '{device_id}' "
            f"(device_type '{device_type}')"
        )

    # c3. df_key is a single key — still wrapped in a dict, since a bare
    # DataFrame is never the top-level return. col=None -> {df_key: df};
    # col=str -> a Series (the one non-dict result, and that's allowed);
    # col=list -> dict of Series, via select_cols.
    result = select_cols(dfs[df_key], df_key, device_id, device_type)
    if col is None:
        return {df_key: result}
    return result

# Examples:
#   get(data)                                                                   # entire loaded dataset, unchanged
#   get(data, "Atmotube")                                                       # all Atmotube device_ids, NOT flattened
#   get(data, "Atmotube", device_id)                                            # one device, flattened to {df_key: df}
#   get(data, "Atmotube", [device_a, device_b])                                 # two devices, each flattened to {df_key: df}
#   get(data, "Atmotube", device_id, "pm")                                      # one df
#   get(data, "Atmotube", device_id, ["pm", "weather"])                         # two dfs, one device
#   get(data, "Atmotube", [device_a, device_b], "pm")                           # same df, two devices, NOT merged
#   get(data, "Atmotube", device_id, "pm", "pm2_5_ugm3_atm")                    # one column
#   get(data, "Atmotube", device_id, "pm", ["pm2_5_ugm3_atm", "pm10_ugm3_atm"]) # two columns


from IPython.display import HTML, display
from IPython.utils.capture import capture_output
import html as html_lib
from typing import TypeVar, Callable

T = TypeVar('T')

def scroll_output(func: Callable[..., T], *args, height: str = "400px", plot_height: str = "800px", center: bool = True, **kwargs) -> T:
    """
    Execute a function, capture output, and render inside a scrollable box.
    Set center=True to horizontally center all content.
    Automatically increases height if plots are detected.
    """
    with capture_output() as captured:
        result = func(*args, **kwargs)

    parts = []
    has_plot = False

    if captured.stdout:
        parts.append(f"<pre>{html_lib.escape(captured.stdout)}</pre>")

    for output in captured.outputs:
        data = output.data
        if "text/html" in data:
            parts.append(data["text/html"])
            # Detect interactive plots (Plotly, Altair, etc. use HTML)
            if any(tag in data["text/html"].lower() for tag in ["plotly", "vega", "bokeh", "script"]):
                has_plot = True
        elif "image/png" in data:
            b64 = data["image/png"]
            parts.append(f'<img src="data:image/png;base64,{b64}" style="max-width:100%;">')
            has_plot = True  # Matplotlib, seaborn, etc.
        elif "text/plain" in data:
            parts.append(f"<pre>{html_lib.escape(data['text/plain'])}</pre>")

    inner_html = "".join(parts)

    # Use appropriate height based on plot detection
    final_height = plot_height if has_plot else height

    # Base styles
    base_style = (
        f"max-height: {final_height}; overflow-y: auto; border: 1px solid #ccc; "
        f"padding: 8px; background: #f5f5f5; color: #000; "
        f"font-family: monospace; white-space: normal;"
    )
    
    # Add centering styles if requested
    if center:
        base_style += " display: flex; flex-direction: column; align-items: center; text-align: center;"

    display(HTML(f'<div style="{base_style}">{inner_html}</div>'))

    return result

# ============================================================================================================
# Helpers for multifiles per device_id in notebooks/

## WARNING: File extraction helpers (legacy method)
## TODO: Remove when migrated to API-based extraction

_DEVICE_KEY_PATTERN = re.compile(r"^(?P<device_id>[A-Za-z0-9]+)_(?P<dates>.+)$")
_DATE_FORMAT = "%d-%b-%Y"


def _parse_device_key(device_key: str):
    """
    Parses a device_id key like 'C7A595F09965_01-May-2026_12-Jun-2026' or
    'DB7A737B8CA0_30-Jun-2026' into (true_id, start_date, end_date).
    If only one date is present, start_date == end_date.
    Returns (None, None, None) if the key doesn't match the expected shape.
    """
    match = _DEVICE_KEY_PATTERN.match(device_key)
    if not match:
        return None, None, None

    true_id = match.group("device_id")
    date_parts = match.group("dates").split("_")

    dates = []
    for part in date_parts:
        try:
            dates.append(datetime.strptime(part.strip(), _DATE_FORMAT))
        except ValueError:
            continue  # skip anything that doesn't parse (e.g. malformed dates)

    if not dates:
        return true_id, None, None
    if len(dates) == 1:
        return true_id, dates[0], dates[0]
    return true_id, dates[0], dates[-1]


def list_device_ids(data: dict, device_type: str) -> list[str]:
    """Returns the sorted, de-duplicated list of true device IDs (serials) for a device_type."""
    ids = set()
    for device_key in data.get(device_type, {}):
        true_id, _, _ = _parse_device_key(device_key)
        if true_id:
            ids.add(true_id)
    return sorted(ids)


def find_files_for_id(data: dict, device_type: str, true_id: str) -> list[str]:
    """Returns all device_id keys (filenames) belonging to one physical device, oldest to newest."""
    matches = []
    for device_key in data.get(device_type, {}):
        parsed_id, start, _ = _parse_device_key(device_key)
        if parsed_id == true_id:
            matches.append((device_key, start))
    matches.sort(key=lambda pair: (pair[1] is None, pair[1]))
    return [key for key, _ in matches]


def latest_file_for_id(data: dict, device_type: str, true_id: str) -> str | None:
    """Returns the device_id key (filename) with the most recent end_date for a given true device ID."""
    matches = []
    for device_key in data.get(device_type, {}):
        parsed_id, _, end = _parse_device_key(device_key)
        if parsed_id == true_id and end is not None:
            matches.append((device_key, end))
    if not matches:
        return None
    matches.sort(key=lambda pair: pair[1])
    return matches[-1][0]

def merge_device_files(data: dict, device_type: str, true_id: str) -> dict[str, pd.DataFrame]:
    """
    Merges all file-chunks belonging to one physical device (true_id) into
    a single {table_name: DataFrame} dict, ordered chronologically.

    Overlapping rows that are IDENTICAL across files are deduplicated,
    keeping the version from the OLDEST file. Overlapping rows with
    DIFFERING values are both kept (resulting in duplicate datetimes) —
    this surfaces the conflict rather than silently picking a winner.
    """
    keys = find_files_for_id(data, device_type, true_id)  # oldest -> newest
    if not keys:
        return {}

    table_frames: dict[str, list[pd.DataFrame]] = {}
    for key in keys:
        content = get(data, device_type, key)  # {table_name: DataFrame}, already unwrapped
        for table_name, df in content.items():
            table_frames.setdefault(table_name, []).append(df)

    merged_tables = {}
    for table_name, dfs in table_frames.items():
        combined = pd.concat(dfs, ignore_index=True)

        if "datetime" in combined.columns:
            # stable sort preserves original (chronological file) order for
            # rows that share the same datetime — required for keep="first"
            # to correctly favor the OLDEST file's version
            combined = combined.sort_values("datetime", kind="stable")

        before = len(combined)
        combined = combined.drop_duplicates(keep="first").reset_index(drop=True)
        dropped = before - len(combined)

        # flag any datetimes that still repeat after dedup — these are
        # genuine conflicts (same timestamp, different values)
        if "datetime" in combined.columns:
            conflict_count = combined["datetime"].duplicated().sum()
            if conflict_count > 0:
                print(
                    f"⚠️ {true_id} / {table_name}: {conflict_count} datetime(s) "
                    f"still duplicated after merge — same timestamp, differing values"
                )

        merged_tables[table_name] = combined

    return merged_tables


def consolidate_device_ids(data: dict, device_type: str) -> dict[str, dict[str, pd.DataFrame]]:
    """
    Merges all file-chunks for every physical device under a device_type
    into one entry per true device ID.

    Returns
    -------
    dict
        { true_device_id: { table_name: merged_DataFrame } }
    """
    ids = list_device_ids(data, device_type)
    return {true_id: merge_device_files(data, device_type, true_id) for true_id in ids}