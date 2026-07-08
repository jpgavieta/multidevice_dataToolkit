import os

REQUIRED_ENV_VARS = ["DB_HOST", "DB_USER", "DB_PASSWORD"]  # extend as needed

def validate_env():
    missing = [v for v in REQUIRED_ENV_VARS if not os.environ.get(v)]
    if missing:
        raise EnvironmentError(f"Missing required env vars: {missing}")