import pandas as pd
import matplotlib.pyplot as plt

# from src.utils import extract_dfs

# ============================================================================================================
# Lil helper functions

def extract_dfs(source: dict) -> dict: # moved here
    """
    Normalize a "subdivided dfs" input into a flat {table_name: df} dict.
    For accepting subdivided 
    per-device dataframes (shared input in stats.py modules).

    Accepts either:
    - the per-device dict produced by transform_device_data()
        (has a "data" key: {table_name: {"df": df, "cols": [...]}})
    - the flat dict returned directly by a parser's parse()
        (table_name: df)

    Lets downstream functions (report_loss, profile_df, check_ranges, etc.)
    accept either shape without each reimplementing this check.
    """
    if "data" in source:
        return {k: v["df"] for k, v in source["data"].items()}
    return {k: v for k, v in source.items() if isinstance(v, pd.DataFrame)}

# Example: extract_dfs(["Atmotube"][device_id])  # device-dict shape
# Example: extract_dfs(atmotube.parse(raw_df))   # flat parser-output shape

def _get_numeric_cols(df):
    """Return all numeric columns except datetime, date, time."""
    skip = {"datetime", "date", "time"}
    return [
        col for col in df.columns
        if col not in skip and pd.api.types.is_numeric_dtype(df[col])
    ]

def _resolve_targets(dfs, df_names, skip):
    """Resolve which dfs to operate on."""
    if df_names:
        invalid = [n for n in df_names if n not in dfs]
        if invalid:
            print(f"df(s) not found: {invalid}. Available: {[k for k in dfs if k not in skip]}")
            return None
        return {n: dfs[n] for n in df_names}
    return {k: v for k, v in dfs.items() if k not in skip}

# ============================================================================================================
# Main stats functions

def report_loss(device, *df_names):
    """
    Reports data quality metrics: row counts, missing values, and coverage %.
    Includes a visual bar for coverage.
    """
    skip = {"all", "gis,", "raw_gis"} 
    dfs = extract_dfs(device)
    if "raw_gis" in device:
        dfs["gis"] = device["raw_gis"] # to see the missing lat/lon
        
    targets = _resolve_targets(dfs, df_names, skip)
    if targets is None:
        return

    # Header: Quality metrics only
    print(f"{'df':<10} {'column':<25} {'rows':>8} {'missing':>8} {'coverage':>10}")
    print("─" * 68)

    for name, df in targets.items():
        total_rows = df.shape[0]
        # Check all columns (numeric and non-numeric) for missing data
        for col in df.columns:
            if col in {"datetime", "date", "time"}:
                continue
                
            missing = df[col].isna().sum()
            coverage = (1 - missing / total_rows) * 100 if total_rows > 0 else 0.0
            
            # Visual bar
            bar_len = int(coverage / 10)
            bar = "█" * bar_len + "░" * (10 - bar_len)
            
            print(f"{name:<10} {col:<25} {total_rows:>8} {missing:>8} {coverage:>8.1f}%  {bar}")
        print()

# report_loss(d1)              # all tables
# report_loss(d1, "pm")        # just pm
# report_loss(d1, "pm", "gas") # pm and gas

def plot_ranges(device, *df_names, window="10min", center="mean", figsize=(10, 4)):
    """
    Plots a range-area chart for each numeric column in the target df(s):
    a shaded band showing the rolling min/max envelope over time, with a
    rolling mean/median line drawn through it.

    One figure per numeric column. Useful for spotting sensor drift, noise
    spikes, or dropouts in a time series at a glance.

    Args:
        device: per-device dict (from transform_device_data) or flat parser dict.
        *df_names: optional names of specific tables to plot (default: all).
        window: rolling window size.
            - If df has a "datetime" column: a pandas time offset string
            (e.g. "10min", "1h", "30s"). Handles irregular sampling
            intervals correctly, since the window always spans the same
            amount of real time regardless of how dense the samples are.
            - If no "datetime" column: pass an integer row count instead.
        center: "mean" or "median" — which line is drawn inside the band.
        figsize: matplotlib figsize per figure.
    """
    skip = {"all", "gis,", "raw_gis"}
    dfs = extract_dfs(device)
    targets = _resolve_targets(dfs, df_names, skip)
    if targets is None:
        return

    for name, df in targets.items():
        numeric_cols = _get_numeric_cols(df)
        if not numeric_cols:
            continue

        has_time = "datetime" in df.columns

        if has_time:
            # Time-based rolling requires a sorted DatetimeIndex
            df = df.sort_values("datetime").set_index("datetime")
        else:
            df = df.reset_index(drop=True)

        x = df.index

        for col in numeric_cols:
            roll = df[col].rolling(window=window, min_periods=1)
            lower = roll.min()
            upper = roll.max()
            line = roll.mean() if center == "mean" else roll.median()

            fig, ax = plt.subplots(figsize=figsize)
            ax.fill_between(x, lower, upper, alpha=0.3, label=f"rolling min/max (window={window})")
            ax.plot(x, line, linewidth=1.2, label=f"rolling {center}")
            ax.set_title(f"{name} — {col}")
            ax.set_xlabel("datetime" if has_time else "index")
            ax.set_ylabel(col)
            ax.legend(loc="upper right", fontsize=8)
            fig.tight_layout()
            plt.show()

# plot_ranges(d1)                          # all tables, default 10-minute window
# plot_ranges(d1, "pm", window="1h")       # just "pm" table, 1-hour smoothing window
# plot_ranges(d1, center="median")         # use rolling median instead of mean

# def profile_df(device, table=None, title=None, minimal=False, theme="flatly",
#                 exclude_cols=None, timeseries_col="datetime"):
#     """
#     Profile a dataframe from a device using ydata-profiling.

#     Parameters
#     -----------
#     device : dict
#         Device data dictionary containing "all" and "data" keys
#     table : str, optional
#         Table name to profile ("pm", "gas", "weather", etc.)
#         If None, profiles the merged "all" dataframe.
#     title : str, optional
#         Custom title for the ProfileReport
#     minimal : bool
#         If True, generates a minimal report (faster). Default False.
#     theme : str
#         HTML theme name (e.g. "flatly", "united"). Default "flatly".
#     exclude_cols : list, optional
#         Column names to exclude from profiling (e.g., ["timezone"])
#     timeseries_col : str, optional
#         Column to set as index before profiling. Default "datetime".
#         Set to None to leave the dataframe's index as-is.

#     Returns
#     --------
#     ProfileReport object
#     """
#     from ydata_profiling import ProfileReport
#     # from ydata_profiling.config import Settings # to customize config settings 

#     if table is None:
#         df = device.get("all")
#         if df is None:
#             raise KeyError("Device has no 'all' merged dataframe to profile — pass a table name instead")
#         df = df.copy()
#         if title is None:
#             title = "Merged Data (All Tables)"
#     else:
#         dfs = extract_dfs(device)
#         if table not in dfs:
#             available = [k for k in dfs if k not in {"all", "gis", "raw_gis"}]
#             raise KeyError(f"Table '{table}' not found. Available tables: {available}")
#         df = dfs[table].copy()
#         if title is None:
#             title = f"Device Data - {table.upper()}"

#     if df is None or df.empty:
#         raise ValueError(f"Dataframe for '{table or 'all'}' is empty or None")

#     if timeseries_col and timeseries_col in df.columns:
#         df = df.set_index(timeseries_col)
#         print(f"Set '{timeseries_col}' as index")

#     if exclude_cols is None:
#         exclude_cols = ["timezone"]
#     cols_to_drop = [col for col in exclude_cols if col in df.columns]
#     if cols_to_drop:
#         df = df.drop(columns=cols_to_drop)
#         print(f"Excluded columns: {cols_to_drop}")

#     print(f"Profiling {title}... Shape: {df.shape}")
#     return ProfileReport(df, title=title, minimal=minimal)