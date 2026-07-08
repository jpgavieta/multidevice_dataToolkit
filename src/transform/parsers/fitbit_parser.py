# transform/parsers/fitbit.py
"""
Parses raw Fitbit / Google Health API responses (from extract/clients/fitbit_client.py)
into per-data-type pandas DataFrames.

SCOPE OF THIS FIRST PASS: flat/simple data types only —
    steps, distance, altitude, floors, sedentary-period, active-minutes,
    active-zone-minutes, heart-rate, heart-rate-variability, oxygen-saturation,
    core-body-temperature, daily-* summary types, sleep, exercise, profile.

NOT covered here yet — deferred to a later pass due to deeper nesting
(waveform arrays, nested alert windows / heartbeats):
    electrocardiogram, irregular-rhythm-notification

NOTE on timestamps: Google's docs state startTime/endTime are always
Z-normalized to UTC on output. So unlike Atmotube (which may report
local device time), NO timezone conversion is needed here — these
values are already UTC as returned. civilStartTime/civilEndTime (local
time) are intentionally dropped during flattening, since UTC is our
storage standard; reconstruct local time downstream in report/ if needed,
using the device's site/timezone from devices.yaml.
"""

import pandas as pd


def _flatten(record: dict, prefix: str = "") -> dict:
    """Flatten a nested dict into dotted-key columns, e.g. {'a': {'b': 1}} -> {'a.b': 1}."""
    flat = {}
    for key, value in record.items():
        full_key = f"{prefix}{key}" if not prefix else f"{prefix}.{key}"
        if isinstance(value, dict):
            flat.update(_flatten(value, full_key))
        elif isinstance(value, list):
            import json
            flat[full_key] = json.dumps(value)  # keep as JSON string, don't explode
        else:
            flat[full_key] = value
    return flat


def _drop_civil_time_cols(df: pd.DataFrame) -> pd.DataFrame:
    """Drop civilStartTime/civilEndTime columns — we store UTC only, not local time."""
    civil_cols = [c for c in df.columns if "civil" in c.lower()]
    return df.drop(columns=civil_cols, errors="ignore")


def _points_to_df(payload: dict) -> pd.DataFrame:
    """
    Turn one data type's raw API response into a flat DataFrame, one row
    per data point. Returns an empty DataFrame (no columns) if there's no
    data for the requested range — not skipped, so callers can distinguish
    "no data" from "this key wasn't fetched at all".
    """
    if payload is None:
        return pd.DataFrame()

    points = payload.get("dataPoints", [])
    if not points:
        return pd.DataFrame()

    records = [_flatten(p) for p in points]
    df = pd.DataFrame(records)
    return _drop_civil_time_cols(df)


# Data types handled by this first pass — matches extract/clients/fitbit_client.py's
# DATA_TYPES minus ecg/irn (handled separately) and minus profile (not a time-series type)
SIMPLE_DATA_TYPES = [
    "steps", "distance", "altitude", "floors",
    "sedentary-period", "active-minutes", "active-zone-minutes",
    "heart-rate", "heart-rate-variability", "oxygen-saturation", "core-body-temperature",
    "daily-resting-heart-rate", "daily-heart-rate-variability", "daily-oxygen-saturation",
    "daily-respiratory-rate", "daily-sleep-temperature-derivations",
    "respiratory-rate-sleep-summary",
    "sleep", "exercise",
]


def parse(raw_data: dict, device_id: str) -> dict:
    """
    Takes the raw dict returned by extract.clients.fitbit_client.extract_raw_data(),
    returns {table_name: DataFrame}, one entry per data type that had data.

    device_id is accepted for signature consistency with other parsers /
    for future use (e.g. tagging rows), even though it's not used to key
    anything here — device identity is handled at the load/join level, per
    our device_assignments design, not baked into the reading rows themselves.
    """
    result = {}

    for data_type in SIMPLE_DATA_TYPES:
        payload = raw_data.get(data_type)
        df = _points_to_df(payload)
        if not df.empty:
            table_name = data_type.replace("-", "_")
            result[table_name] = df

    if raw_data.get("profile"):
        result["profile"] = pd.DataFrame([_flatten(raw_data["profile"])])

    return result