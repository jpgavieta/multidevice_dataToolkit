import pandas as pd
import matplotlib.pyplot as plt

import numpy as np
from src.utils import get
from typing import Mapping
from IPython.display import display

# ============================================================================================================
# Helpers

def _get_numeric_cols(df: pd.DataFrame) -> list[str]:
    """Return all numeric columns except datetime, date, time."""
    skip = {"datetime", "date", "time"}
    return [
        col for col in df.columns
        if col not in skip and pd.api.types.is_numeric_dtype(df[col])
    ]

def _resolve_targets(dfs: Mapping[str, pd.DataFrame], df_names: tuple[str, ...], skip: set[str]) -> dict[str, pd.DataFrame] | None:
    """Resolve which dfs to operate on."""
    if df_names:
        invalid = [n for n in df_names if n not in dfs]
        if invalid:
            print(f"df(s) not found: {invalid}. Available: {[k for k in dfs if k not in skip]}")
            return None
        return {n: dfs[n] for n in df_names}
    return {k: v for k, v in dfs.items() if k not in skip}


import pandas as pd

def filter_date_range(
    device: dict[str, pd.DataFrame],
    start: str | pd.Timestamp | None = None,
    end: str | pd.Timestamp | None = None,
) -> dict[str, pd.DataFrame]:
    """
    Returns a new {table_name: DataFrame} dict, each table filtered to rows
    where 'datetime' falls within [start, end] (inclusive). Tables without
    a 'datetime' column, or with start/end left as None, pass through
    unfiltered on that bound.
    """
    start_ts = pd.Timestamp(start, tz="UTC") if start is not None else None
    end_ts = pd.Timestamp(end, tz="UTC") if end is not None else None

    filtered = {}
    for table_name, df in device.items():
        if "datetime" not in df.columns:
            filtered[table_name] = df
            continue

        mask = pd.Series(True, index=df.index)
        if start_ts is not None:
            mask &= df["datetime"] >= start_ts
        if end_ts is not None:
            mask &= df["datetime"] <= end_ts

        filtered[table_name] = df[mask].reset_index(drop=True)

    return filtered



def report_loss(dfs, *df_names):
    """
    Reports data quality metrics: row counts, missing values, and coverage %.
    Includes a visual bar for coverage.
    """
    if not dfs:
        print("⚠️ No data to report on.")
        return
    if not isinstance(dfs, dict):
        raise TypeError(f"dfs must be a dict of DataFrames; got {type(dfs)}")

    skip = {"all"}
    targets = _resolve_targets(dfs, df_names, skip)
    if targets is None:
        return

    print(f"{'df':<10} {'column':<25} {'rows':>8} {'missing':>8} {'coverage':>10}")
    print("─" * 68)

    for name, df in targets.items():
        if df is None:
            continue
        total_rows = df.shape[0]
        for col in df.columns:
            if col in {"datetime", "date", "time"}:
                continue

            missing = df[col].isna().sum()
            coverage = (1 - missing / total_rows) * 100 if total_rows > 0 else 0.0

            bar_len = int(coverage / 10)
            bar = "█" * bar_len + "░" * (10 - bar_len)

            print(f"{name:<10} {col:<25} {total_rows:>8} {missing:>8} {coverage:>8.1f}%  {bar}")
        print()

import pandas as pd

def report_ranges(dfs, window="10D", center="median", *df_names):
    # reuse your local helpers exactly like your existing function does
    if not dfs:
        return pd.DataFrame()
    if not isinstance(dfs, dict):
        raise TypeError(f"dfs must be a dict of DataFrames; got {type(dfs)}")

    skip = {"all"}
    targets = _resolve_targets(dfs, df_names, skip)
    if targets is None:
        return pd.DataFrame()

    center_mode = center.lower() if isinstance(center, str) else "median"
    if center_mode not in {"mean", "median"}:
        center_mode = "median"

    rows = []

    for name, df in targets.items():
        if df is None:
            continue
        if "datetime" not in df.columns:
            continue

        df = df.dropna(subset=["datetime"]).sort_values("datetime").set_index("datetime")
        numeric_cols = _get_numeric_cols(df)

        for col in numeric_cols:
            s = df[col].astype(float).dropna()
            n = int(s.shape[0])
            if n == 0:
                continue

            g_min = float(s.min())
            g_q25 = float(s.quantile(0.25))
            g_med = float(s.median())
            g_mean = float(s.mean())
            g_q75 = float(s.quantile(0.75))
            g_max = float(s.max())

            s = s.sort_index()
            r = s.rolling(window=window, min_periods=1)

            roll_min = r.min()
            roll_max = r.max()
            roll_med = r.median()
            roll_mean = r.mean()
            roll_center = roll_mean if center_mode == "mean" else roll_med

            rows.append({
                "df": name,
                "column": col,
                "n": n,

                "global_min": g_min,
                "global_q25": g_q25,
                "global_med": g_med,
                "global_mean": g_mean,
                "global_q75": g_q75,
                "global_max": g_max,

                "roll_min_med": float(roll_min.median()),
                "roll_center_med": float(roll_center.median()),
                "roll_max_med": float(roll_max.median()),
                "roll_center_mean": float(roll_center.mean()),
                "roll_window_min": float(roll_min.min()),
                "roll_window_max": float(roll_max.max()),
            })

    return pd.DataFrame(rows)



def plot_ranges(dfs, window=None, center=None, figsize=None, plot=True, *df_names):
    """
    Plot data ranges for the given DataFrames.

    Parameters:
    -----------
    dfs : dict[str, pd.DataFrame]
        Dictionary of {table_name: DataFrame}
    window : int, optional
        Rolling window size (default: 10)
    center : bool, optional
        Choose the center line: if center == "mean" uses rolling mean, else uses rolling median
        (use "mean" or "median" or True/False).
    figsize : tuple, optional
        Figure size
    plot : bool, optional
        Whether to display plots (default: True)
    *df_names : str
        Specific table names to plot (if empty, plots all)
    """
    if not dfs:
        return
    if not isinstance(dfs, dict):
        raise TypeError(f"dfs must be a dict of DataFrames; got {type(dfs)}")

    if window is None:
        window = 10

    skip = {"all"}
    targets = _resolve_targets(dfs, df_names, skip)
    if targets is None:
        return

    for name, df in targets.items():
        if df is None:
            continue

        numeric_cols = _get_numeric_cols(df)
        if not numeric_cols:
            continue

        has_time = "datetime" in df.columns
        if has_time:
            df = df.dropna(subset=["datetime"]).sort_values("datetime").set_index("datetime")
        else:
            df = df.reset_index(drop=True)

        # x-axis: datetime index if present
        x = df.index.to_numpy() if has_time else np.arange(len(df))

        # choose which statistic to draw as the "center" line
        if isinstance(center, str):
            center_mode = center.lower()
        elif center is True:
            center_mode = "mean"
        else:
            center_mode = "median"

        for col in numeric_cols:
            s = df[col].astype(float)
            s = s.dropna()
            if has_time:
                s = s.sort_index()

            roll = s.rolling(window=window, min_periods=1)

            # Rolling IQR band (25th–75th)
            q25 = roll.quantile(0.25).to_numpy(dtype=float)
            q75 = roll.quantile(0.75).to_numpy(dtype=float)

            # Rolling center line
            y_med = roll.median().to_numpy(dtype=float)
            y_mean = roll.mean().to_numpy(dtype=float)
            y_center = y_mean if center_mode == "mean" else y_med

            fig, ax = plt.subplots(figsize=figsize)
            xs = s.index.to_numpy() if has_time else np.arange(len(s))

            ax.fill_between(xs, q25, q75, alpha=0.5, color="steelblue", label="rolling IQR (25–75)")
            ax.plot(xs, y_center, color="darkred", linewidth=0.5, label=f"rolling {center_mode}", zorder=5)

            ax.set_title(f"{name} — {col}")
            ax.set_xlabel("datetime" if has_time else "index")
            ax.set_ylabel(col)
            ax.legend(loc="upper right", fontsize=8)

            fig.tight_layout()
            if plot:
                display(fig)
            plt.close(fig)

