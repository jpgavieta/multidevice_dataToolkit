"""
Out-of-range reading detector for Atmotube PRO data.

Flags sensor readings that fall outside Atmotube PRO's documented
measurement ranges.

Source: https://support.atmotube.com/en/articles/10301124-atmotube-pro-technical-specifications

Designed to plug into multidevice_dataToolkit's existing shapes — accepts
either:
  - the per-device dict from transform_device_data()
    (i.e. transformed["Atmotube"][device_id] — same shape report_loss() takes)
  - OR the flat dict returned directly by a parser's parse()
    (i.e. {"pm": df, "weather": df, "gas": df, ...})

Usage
-----
    from src.range_check import check_ranges, check_value

    check_ranges(transformed["Atmotube"][device_id])               # all tables
    check_ranges(transformed["Atmotube"][device_id], "pm", "gas")   # just these
    flagged_df = check_ranges(d1)                                   # capture flagged rows

    check_value("pm2_5", 1200)   # ad hoc single-value check
"""

import pandas as pd

from src.utils import extract_dfs

# ============================================================================================================
# Range specs
# Column names match what src/etl/parsers/atmotube.py produces
# (build_pm_df / build_weather_df / build_gas_df).
#
# documented=True  -> range is stated directly on the Atmotube PRO spec page
# documented=False -> not stated on that page; using a reasonable default
#                      (verify before relying on it for anything critical)

RANGE_SPECS = {
    "pm1_0_ugm3_atm": dict(low=1,   high=1000, unit="\u00b5g/m\u00b3", documented=True,  note=""),
    "pm2_5_ugm3_atm": dict(low=1,   high=1000, unit="\u00b5g/m\u00b3", documented=True,  note=""),
    "pm10_ugm3_atm":  dict(low=1,   high=1000, unit="\u00b5g/m\u00b3", documented=True,  note=""),
    "tvoc_ppm":       dict(low=0,   high=60,   unit="ppm",   documented=True,  note=""),
    "temp_c":         dict(low=0,   high=65,   unit="\u00b0C", documented=True,
                            note="\u00b11\u00b0C accuracy is only rated within this range"),
    "hum_pct":        dict(low=0,   high=100,  unit="%RH",   documented=False,
                            note="physical limit only, not stated on the spec page \u2014 verify"),
    "press_hpa":      dict(low=300, high=1100, unit="hPa",   documented=False,
                            note="typical BME280 operating range, not on the spec page \u2014 verify"),
}

# tvoc_index, nox_index, co2_ppm, aqs_total, and the raw particle-count / pmsize columns
# come from PRO-2-only sensors and features and aren't on the PRO spec page, so they're
# intentionally left unconfigured here. Add entries for them if you start validating PRO 2 data.


# ============================================================================================================
# Batch checker (main entry point)

def check_ranges(device: dict, *table_names: str) -> pd.DataFrame:
    """
    Flag readings outside Atmotube PRO's documented measurement ranges.

    Mirrors report_loss()'s call pattern:
        check_ranges(d1)                # all tables
        check_ranges(d1, "pm")          # just pm
        check_ranges(d1, "pm", "gas")   # pm and gas

    Only checks columns with a configured entry in RANGE_SPECS. Prints a
    per-column summary (rows checked, rows flagged, % in range) and returns
    a DataFrame listing every flagged reading (empty DataFrame if none found).
    """
    dfs = extract_dfs(device)

    if table_names:
        missing = [n for n in table_names if n not in dfs]
        if missing:
            print(f"Table(s) not found: {missing}. Available: {list(dfs.keys())}")
            return pd.DataFrame()
        dfs = {n: dfs[n] for n in table_names}

    flagged_rows = []

    print(f"{'table':<10}{'column':<18}{'rows':>8}{'flagged':>10}{'in range':>10}")
    print("\u2500" * 60)

    for table, df in dfs.items():
        for col, spec in RANGE_SPECS.items():
            if col not in df.columns:
                continue

            values = pd.to_numeric(df[col], errors="coerce")
            n_total = int(values.notna().sum())
            if n_total == 0:
                continue

            out_of_range = (values < spec["low"]) | (values > spec["high"])
            n_flagged = int(out_of_range.sum())
            pct_in_range = (1 - n_flagged / n_total) * 100
            bar = "\u2588" * int(pct_in_range / 10) + "\u2591" * (10 - int(pct_in_range / 10))
            verify = "" if spec["documented"] else "  (unverified default range)"
            print(f"{table:<10}{col:<18}{n_total:>8}{n_flagged:>10}{pct_in_range:>9.1f}%  {bar}{verify}")

            if n_flagged:
                flagged_values = values[out_of_range]
                detail = pd.DataFrame({
                    "datetime": df.loc[out_of_range, "datetime"].values if "datetime" in df.columns else pd.NA,
                    "table": table,
                    "column": col,
                    "value": flagged_values.values,
                    "status": ["below_range" if v < spec["low"] else "above_range" for v in flagged_values],
                    "valid_range": f"{spec['low']}-{spec['high']} {spec['unit']}",
                    "documented": spec["documented"],
                })
                flagged_rows.append(detail)

        print()

    if not flagged_rows:
        print("No out-of-range readings found.")
        return pd.DataFrame(columns=["datetime", "table", "column", "value", "status", "valid_range", "documented"])

    result = pd.concat(flagged_rows, ignore_index=True)
    if "datetime" in result.columns and result["datetime"].notna().any():
        result = result.sort_values("datetime").reset_index(drop=True)
    return result


# ============================================================================================================
# Single-value checker (ad hoc / interactive use)

ALIASES = {
    "pm1_0_ugm3_atm": ["pm1", "pm1.0", "pm1_0"],
    "pm2_5_ugm3_atm": ["pm2.5", "pm2_5", "pm25"],
    "pm10_ugm3_atm":  ["pm10"],
    "tvoc_ppm":       ["tvoc", "voc"],
    "temp_c":         ["temp", "temperature"],
    "hum_pct":        ["hum", "humidity", "rh"],
    "press_hpa":      ["press", "pressure"],
}


def _resolve_metric(name: str):
    key = name.strip().lower()
    if key in RANGE_SPECS:
        return key
    for canonical, variants in ALIASES.items():
        if key in variants:
            return canonical
    return None


def check_value(metric: str, value: float) -> str:
    """Check a single value against its documented range. Returns a message string."""
    canonical = _resolve_metric(metric)
    if canonical is None:
        return f"No range configured for '{metric}'"

    spec = RANGE_SPECS[canonical]
    if value < spec["low"]:
        status = "below range"
    elif value > spec["high"]:
        status = "above range"
    else:
        status = "in range"

    flag = "" if spec["documented"] else " (undocumented default range \u2014 verify)"
    return (
        f"{canonical}: {value} {spec['unit']} is {status} "
        f"(valid: {spec['low']}-{spec['high']} {spec['unit']}){flag}"
    )

# Example: check_value("pm2_5", 1200)
#          -> "pm2_5_ugm3_atm: 1200 µg/m³ is above range (valid: 1-1000 µg/m³)"