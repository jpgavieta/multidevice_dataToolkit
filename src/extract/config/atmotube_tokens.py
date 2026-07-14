# src/extract/config/atmotube_tokens.py
"""
Atmotube Cloud static API key + per-device MAC mapping.
- API Key: Loaded from ./secrets/atmotube/api_key.json
- MAC Credentials: Loaded from ./secrets/atmotube/.env.access (via environment variables)
NOTE: Each _tokens.py module NEVER touch each other — ONLY tokens.py
"""

import os
import json
from pathlib import Path
from dotenv import load_dotenv

CONFIG_DIR = Path(__file__).resolve().parent
SECRETS_DIR = CONFIG_DIR / "secrets" / "atmotube"

API_KEY_FILE = SECRETS_DIR / "api_key.json"
ENV_ACCESS_FILE = SECRETS_DIR / ".env.access"

def _ensure_env_loaded():
    if ENV_ACCESS_FILE.exists():
        load_dotenv(dotenv_path=ENV_ACCESS_FILE, override=False)
    else:
        raise FileNotFoundError(f"Atmotube credentials not found at {ENV_ACCESS_FILE}")
    
def _load_api_key() -> str:
    if not API_KEY_FILE.exists():
        raise FileNotFoundError(f"API Key not found at {API_KEY_FILE}")
    
    raw = json.loads(API_KEY_FILE.read_text())
    return raw.get("api_key") or raw.get("key")

def get_api_key() -> str:
    return _load_api_key()

def get_mac_for_device(device_id: str) -> str:
    """
    Returns MAC for device_id (e.g., 'atmotube_kol_07').
    Looks for env var: ATMOTUBE_KOL_07_MAC
    """
    _ensure_env_loaded()
    
    # Extract 'KOL_07' from 'atmotube_kol_07'
    # Assumes format: prefix_KOL_XX
    parts = device_id.split("_")
    if len(parts) < 3:
        raise ValueError(f"Invalid device_id format: '{device_id}'. Expected 'atmotube_kol_XX'")
    
    # Reconstruct suffix: KOL_07
    suffix = "_".join(parts[1:]).upper()
    
    env_key = f"ATMOTUBE_{suffix}_MAC"
    mac = os.getenv(env_key)
    
    if not mac:
        available = [k for k in os.environ.keys() if k.startswith("ATMOTUBE_") and k.endswith("_MAC")]
        raise KeyError(
            f"MAC not found for '{device_id}'. Looked for '{env_key}'. "
            f"Available: {available}"
        )
    return mac