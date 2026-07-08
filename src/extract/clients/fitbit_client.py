# extract/clients/fitbit_client.py

"""
Fitbit / Google Health data pull — per device, per date range.
Returns raw API responses;, no participant logic.
"""

from datetime import datetime, timedelta

import requests

from extract.config.tokens import get_fitbit_token

BASE_URL = "https://health.googleapis.com/v4"

# data type identifiers and respective scopes : https://developers.google.com/health/data-types

DATA_TYPES = [  
    # scope: activity_and_fitness
    "steps",                        # interval
    "distance",                     # interval
    "altitude",                     # interval
    "sedentary-period",             # interval
    "exercise",                     # session, note: gps coordinates as routes data within ExerciseSessionRecord
    "active-minutes",               # interval, based on montion sensor + heart rate  
    "active-zone-minutes",          # interval, note: based on heart rate
    "floors",                       # interval

    # scope: health_metrics_and_measurements          
    "heart-rate",                   # sample
    "daily-resting-heart-rate",     # daily avg
    "daily-heart-rate-zones",       # daily avg
    "heart-rate-variability",       # sample
    "daily-heart-rate-variability", # daily avg
    "daily-respiratory-rate",       # daily avg
    "oxygen-saturation",            # sample
    "daily-oxygen-saturation",      # daily avg
    "daily-respiratory-rate",       # daily avg
    "respiratory-rate-sleep-summary", # sample
    "core-body-temperature",        # sampe, note: based on skin temp
    "daily-sleep-temperature-derivations", # daily avg, note: only for night

    # scope: sleep
    "sleep",                        # session
    # scope: irn
    "irregular-rhythm-notification",# session
    # scope: ecg
    "electrocardiogram"             # session
]

# REST field path to filter on for each data type, used in the API request : https://developers.google.com/health/reference/rest/v4/users.dataTypes.dataPoints/list

FILTER_FIELDS = {
    # Interval type
    "steps": "steps.interval.start_time",
    "distance": "distance.interval.start_time",
    "altitude": "altitude.interval.start_time",
    "floors": "floors.interval.start_time",
    "sedentary-period": "sedentary_period.interval.start_time",
    "active-minutes": "active_minutes.interval.start_time",
    "active-zone-minutes": "active_zone_minutes.interval.start_time",

    # Sample type
    "heart-rate": "heart_rate.sample_time.physical_time",
    "heart-rate-variability": "heart_rate_variability.sample_time.physical_time",
    "oxygen-saturation": "oxygen_saturation.sample_time.physical_time",
    "core-body-temperature": "core_body_temperature.sample_time.physical_time",
    "respiratory-rate-sleep-summary": "respiratory_rate_sleep_summary.sample_time.physical_time",

    # Daily type
    "daily-resting-heart-rate": "daily_resting_heart_rate.date",
    "daily-heart-rate-variability": "daily_heart_rate_variability.date",
    "daily-heart-rate-zones": "daily_heart_rate_zones.date",
    "daily-oxygen-saturation": "daily_oxygen_saturation.date",
    "daily-respiratory-rate": "daily_respiratory_rate.date",
    "daily-sleep-temperature-derivations": "daily_sleep_temperature_derivations.date",

    # Session type
    "sleep": "sleep.interval.end_time",
    "exercise": "exercise.interval.start_time",
    "irregular-rhythm-notification": "irregular_rhythm_notification.interval.start_time",
    "electrocardiogram": "electrocardiogram.interval.start_time",
}


def _get_data_points(access_token: str, data_type: str, start_date: str, end_date: str) -> dict:
    field = FILTER_FIELDS.get(data_type)
    if field is None:
        raise ValueError(f"No filter field configured for data type '{data_type}'")

    end_exclusive = (datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
    filter_expr = f'{field} >= "{start_date}T00:00:00Z" AND {field} < "{end_exclusive}T00:00:00Z"'

    resp = requests.get(
        f"{BASE_URL}/users/me/dataTypes/{data_type}/dataPoints",
        headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
        params={"filter": filter_expr},
    )
    resp.raise_for_status()
    return resp.json()


def _get_profile(access_token: str) -> dict:
    resp = requests.get(
        f"{BASE_URL}/users/me/profile",
        headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
    )
    resp.raise_for_status()
    return resp.json()


def extract_raw_data(device_id: str, start_date: str, end_date: str) -> dict:
    """
    Pulls all Fitbit data types for one device over one date range.
    Returns: {"steps": {...}, "heart-rate": {...}, "sleep": {...}, "distance": {...}, "profile": {...}}
    Any single data type failing doesn't stop the others.
    """
    access_token = get_fitbit_token(device_id)
    raw = {}

    for dt in DATA_TYPES:
        try:
            raw[dt] = _get_data_points(access_token, dt, start_date, end_date)
        except (requests.HTTPError, ValueError) as e:
            print(f"  ⚠️ '{device_id}' failed to fetch '{dt}': {e}")
            raw[dt] = None

    try:
        raw["profile"] = _get_profile(access_token)
    except requests.HTTPError as e:
        print(f"  ⚠️ '{device_id}' failed to fetch profile: {e}")
        raw["profile"] = None

    return raw