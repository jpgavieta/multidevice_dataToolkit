# src/extract/scripts/inspect_data_fitbit.py
"""
Ad-hoc inspector for a single Fitbit data type — prints the raw response
(or first data point) so you can confirm response shapes, debug filter
errors, or verify a fix against the real API before wiring it into
fitbit_client.py properly.

Not part of the pipeline — this is a debugging tool, run manually.

USAGE:
    # First data point only (default) — for checking response shape
    python -m extract.scripts.inspect_data_fitbit fitbit_kol_01 daily-resting-heart-rate

    # Full response, not just first point
    python -m extract.scripts.inspect_data_fitbit fitbit_kol_01 floors --full

    # Custom date range (default: last 14 days — safe for any rollup type's
    # duration cap; widen deliberately if you need more history)
    python -m extract.scripts.inspect_data_fitbit fitbit_kol_01 exercise --start 2026-01-10 --end 2026-07-09

    # Force dailyRollUp instead of dataPoints.list, for types not yet added
    # to DAILY_ROLLUP_TYPES in fitbit_client.py
    python -m extract.scripts.inspect_data_fitbit fitbit_kol_01 floors --rollup
"""

import argparse
import json
from datetime import date, timedelta

from extract.config.tokens import get_fitbit_token
from extract.clients.fitbit_client import (
    _get_data_points,
    _get_daily_rollup,
    DAILY_ROLLUP_TYPES,
)


def main():
    parser = argparse.ArgumentParser(description="Inspect a raw Fitbit API response for one data type.")
    parser.add_argument("device_id")
    parser.add_argument("data_type")
    parser.add_argument("--start", default=str(date.today() - timedelta(days=14)))
    parser.add_argument("--end", default=str(date.today()))
    parser.add_argument("--full", action="store_true", help="Print the full response, not just the first point")
    parser.add_argument("--rollup", action="store_true", help="Force dailyRollUp, even if data_type isn't in DAILY_ROLLUP_TYPES yet")
    args = parser.parse_args()

    token = get_fitbit_token(args.device_id)
    use_rollup = args.rollup or args.data_type in DAILY_ROLLUP_TYPES

    if use_rollup:
        resp = _get_daily_rollup(token, args.data_type, args.start, args.end)
        points = resp.get("rollupDataPoints", [])
    else:
        resp = _get_data_points(token, args.data_type, args.start, args.end)
        points = resp.get("dataPoints", [])

    print(f"\n{args.data_type}: {len(points)} data point(s) [{args.start} → {args.end}]")

    if args.full:
        print(json.dumps(resp, indent=2))
    elif points:
        print(json.dumps(points[0], indent=2))


if __name__ == "__main__":
    main()