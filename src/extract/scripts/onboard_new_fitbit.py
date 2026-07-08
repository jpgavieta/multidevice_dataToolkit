"""
extract/scripts/onboard_new_fitbit.py

One-time setup for a new Fitbit device: runs the Google OAuth consent flow
and saves the resulting token so future pulls run silently.

Run this ONCE per new device, after:
    1.  The device's Google account must first be added as a Test User in the
        Google Cloud Console (OAuth consent screen > Audience).
    2.  You must know the device_id you're about to assign it (check config
        conventions, e.g. fitbit_kol_08).

USAGE:
    python -m extract.scripts.onboard_new_fitbit fitbit_kol_08

A browser window will open — sign in to THIS DEVICE'S Google account
(not your own), and approve the requested permissions.
"""

import sys
from datetime import date, timedelta

from extract.clients.fitbit_client import extract_raw_data


def main():
    if len(sys.argv) != 2:
        print("Usage: python -m extract.scripts.onboard_new_fitbit <device_id>")
        sys.exit(1)

    device_id = sys.argv[1]
    end = date.today()
    start = end - timedelta(days=7)  # short test range, not a real backfill

    print(f"\nOnboarding '{device_id}' — a browser window should open shortly.")
    print("Sign in to THIS DEVICE'S Google account, not your own.\n")

    result = extract_raw_data(device_id, str(start), str(end))

    print(f"\n=== Results for '{device_id}' ===")
    for data_type, payload in result.items():
        if payload is None:
            print(f"  {data_type}: FAILED")
        else:
            print(f"  {data_type}: OK")

    print(f"\nToken saved. '{device_id}' is ready for regular pulls.")


if __name__ == "__main__":
    main()