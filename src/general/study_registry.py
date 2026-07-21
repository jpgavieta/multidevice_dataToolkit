# src/general/device_registry.py
import os
import yaml
from pathlib import Path
from typing import Any
from dotenv import load_dotenv
from yaml_env_tag import construct_env_tag

# ============================================================================================================

# Register !ENV constructor globally on SafeLoader (do this once at module level)
yaml.SafeLoader.add_constructor("!ENV", construct_env_tag)

def load_yaml_with_env(config_path: str) -> Any:
    """
    Reusable helper to load a YAML file with !ENV tag support.
    Automatically loads all .env files from extract/config/secrets before parsing.
    """
    # Load secrets from all files in the secrets directory
    SECRETS_DIR = Path(__file__).resolve().parents[1] / "extract" / "config" / "secrets"
    if SECRETS_DIR.exists():
        for env_file in SECRETS_DIR.rglob(".env.access"):
            load_dotenv(dotenv_path=env_file, override=False)

    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found at {path}")

    with open(path, "r", encoding="utf-8") as f:
        # safe_load now recognizes !ENV due to global registration
        return yaml.safe_load(f)

def load_devices(config_path: str = "config/devices.yml") -> list[dict[str, Any]]:
    """
    Load and flatten device entries from a YAML registry.
    Expects a mapping at the YAML root where keys ending in "_devices" contain a list of device objects.
    """
    raw = load_yaml_with_env(config_path)

    if not isinstance(raw, dict):
        raise ValueError("Device registry root must be a mapping")

    devices: list[dict[str, Any]] = []
    for key, entries in raw.items():
        if not key.endswith("_devices") or not entries:
            continue
        for d in entries:
            if "id" not in d or "type" not in d:
                raise ValueError(f"Malformed device entry in '{key}': {d}")
            devices.append(d)

    return devices   

def load_participants(config_path: str = "config/participants.yml") -> list[dict[str, Any]]:
    """
    Load and flatten participant entries from a YAML registry.
    Expects a mapping at the YAML root with a "study_participants" list.
    Each participant may include a nested "device_assignments" list, which is left intact (not flattened) so callers can process assignments per participant.
    """
    raw = load_yaml_with_env(config_path)

    if not isinstance(raw, dict):
        raise ValueError("Participant registry root must be a mapping")

    participants = raw.get("study_participants")
    if not participants:
        raise ValueError("Expected 'study_participants' key with a non-empty list")

    for p in participants:
        if "id" not in p:
            raise ValueError(f"Malformed participant entry: {p}")

    return participants