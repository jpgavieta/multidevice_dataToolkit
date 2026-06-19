import pandas as pd

from ydata_profiling import ProfileReport
from ydata_profiling import ProfileReport
from ydata_profiling.config import Settings


# def _get_numeric_cols(df):
#     """Return all numeric columns except datetime, date, time."""
#     skip = {"datetime", "date", "time"}
#     return [
#         col for col in df.columns
#         if col not in skip and pd.api.types.is_numeric_dtype(df[col])
#     ]

def _resolve_targets(dfs, df_names, skip):
    """Resolve which dfs to operate on."""
    if df_names:
        invalid = [n for n in df_names if n not in dfs]
        if invalid:
            print(f"df(s) not found: {invalid}. Available: {[k for k in dfs if k not in skip]}")
            return None
        return {n: dfs[n] for n in df_names}
    return {k: v for k, v in dfs.items() if k not in skip}


def report_loss(device, *df_names):
    skip    = {"all", "gis,", "raw_gis"}
    dfs     = {k: v["df"] for k, v in device["data"].items()}
    dfs["gis"] = device["raw_gis"]                                  # to see missing lon/lat shit
    targets = _resolve_targets(dfs, df_names, skip)
    if targets is None:
        return

    print(f"{'df':<10} {'column':<25} {'rows':>8} {'missing':>8} {'coverage':>10}")
    print("─" * 68)

    for name, df in targets.items():
        total_rows = df.shape[0]          # ← per-df row count
        for col in df.columns:
            if col in {"datetime", "date", "time"}:
                continue
            missing  = df[col].isna().sum()
            coverage = (1 - missing / total_rows) * 100
            bar      = "█" * int(coverage / 10) + "░" * (10 - int(coverage / 10))
            print(f"{name:<10} {col:<25} {total_rows:>8} {missing:>8} {coverage:>8.1f}%  {bar}")
        print()

# report_loss(d1)              # all tables
# report_loss(d1, "pm")        # just pm
# report_loss(d1, "pm", "gas") # pm and gas

# def profile_df(df, title=None):
#     """Generate an interactive profile report for a dataframe.

#     Parameters
#     ----------
#     df    : pd.DataFrame
#     title : str, optional
#     """
#     from ydata_profiling import ProfileReport
#     return ProfileReport(df, title=title, minimal=False)

# # Example: profile_df(d1["data"]["pm"]["df"], title="PM - Device 1").to_notebook_iframe()
# # Example: profile_df(d1["all"], title="All - Device 1").to_notebook_iframe()

def profile_df(device, table=None, title=None, minimal=False, theme="flatly",
                exclude_cols=None, timeseries_col="datetime"):
    """
    Profile a dataframe from a device using ydata-profiling.

    Parameters
    -----------
    device : dict
        Device data dictionary containing "all" and "data" keys
    table : str, optional
        Table name to profile ("pm", "gas", "weather", etc.)
        If None, profiles the merged "all" dataframe.
    title : str, optional
        Custom title for the ProfileReport
    minimal : bool
        If True, generates a minimal report (faster). Default False.
    theme : str
        HTML theme name (e.g. "flatly", "united"). Default "flatly".
    exclude_cols : list, optional
        Column names to exclude from profiling (e.g., ["timezone"])
    timeseries_col : str, optional
        Column to set as index before profiling. Default "datetime".
        Set to None to leave the dataframe's index as-is.

    Returns
    --------
    ProfileReport object
    """
    from ydata_profiling import ProfileReport

    if "all" not in device or "data" not in device:
        raise KeyError("Device must contain 'all' and 'data' keys")

    if table is None:
        df = device["all"].copy()
        if title is None:
            title = "Merged Data (All Tables)"
    else:
        if table not in device["data"]:
            available = list(device["data"].keys())
            raise KeyError(f"Table '{table}' not found. Available tables: {available}")
        df = device["data"][table]["df"].copy()
        if title is None:
            title = f"Device Data - {table.upper()}"

    if df is None or df.empty:
        raise ValueError(f"Dataframe for '{table or 'all'}' is empty or None")

    if timeseries_col and timeseries_col in df.columns:
        df = df.set_index(timeseries_col)
        print(f"Set '{timeseries_col}' as index")

    if exclude_cols is None:
        exclude_cols = ["timezone"]
    cols_to_drop = [col for col in exclude_cols if col in df.columns]
    if cols_to_drop:
        df = df.drop(columns=cols_to_drop)
        print(f"Excluded columns: {cols_to_drop}")

    print(f"Profiling {title}... Shape: {df.shape}")
    return ProfileReport(df, title=title, minimal=minimal)