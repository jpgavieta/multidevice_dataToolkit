#!/usr/bin/env python3
"""
Seed study.devices, study.participants, and study.device_assignments from config/devices.yml and config/participants.yml.

Safe to re-run: uses ON CONFLICT DO NOTHING throughout.
"""
import os
import psycopg2
from psycopg2.extras import execute_values

from general.study_registry import load_devices, load_participants


def get_conn():
    return psycopg2.connect(
        dbname=os.environ["DB_NAME"],
        host=os.environ["DB_HOST"],
        port=os.environ["DB_PORT"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
    )


def seed_devices(cur, devices: list[dict]) -> int:
    rows = [
        (
            d["id"],
            d["type"],
            d.get("site"),
            d.get("timezone"),
            d.get("start_date"),
            d.get("end_date"),
            d.get("notes"),
        )
        for d in devices
    ]
    execute_values(
        cur,
        """
        INSERT INTO study.devices (id, device_type, site, timezone, start_date, end_date, notes)
        VALUES %s
        ON CONFLICT (id) DO NOTHING
        """,
        rows,
    )
    return len(rows)


def seed_participants(cur, participants: list[dict]) -> int:
    rows = [
        (p["id"], p.get("site"), p.get("enrolled_at"), p.get("notes"))
        for p in participants
    ]
    execute_values(
        cur,
        """
        INSERT INTO study.participants (id, site, enrolled_at, notes)
        VALUES %s
        ON CONFLICT (id) DO NOTHING
        """,
        rows,
    )
    return len(rows)


def seed_assignments(cur, participants: list[dict]) -> int:
    rows = []
    for p in participants:
        for a in p.get("device_assignments") or []:
            rows.append(
                (p["id"], a["device_id"], a["assigned_from"], a.get("assigned_until"))
            )
    if not rows:
        return 0
    execute_values(
        cur,
        """
        INSERT INTO study.device_assignments
            (participant_id, device_id, assigned_from, assigned_until)
        VALUES %s
        ON CONFLICT DO NOTHING
        """,
        rows,
    )
    return len(rows)


def main():
    devices = load_devices()
    participants = load_participants()

    conn = get_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                n_dev = seed_devices(cur, devices)
                n_part = seed_participants(cur, participants)
                n_assign = seed_assignments(cur, participants)
        print(f"Seeded: {n_dev} devices, {n_part} participants, {n_assign} device_assignments")
    finally:
        conn.close()


if __name__ == "__main__":
    main()