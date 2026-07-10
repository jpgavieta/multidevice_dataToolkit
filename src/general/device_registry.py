# general/device_registry.py
import yaml
from pathlib import Path
from typing import Any

def load_devices(config_path: str = "config/devices.yml") -> list[dict[str, Any]]:
    """
    Load and flatten device entries from a YAML registry.
    Expects a mapping at the YAML root where keys ending in "_devices" contain a list of device objects. Each device object must include:
        - "id"
        - "type"

    Returns: a flat list of device dicts (e.g., [{"type": "...", "id": "...", ...}, ...]).
    """
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Device registry not found at {path}")

    with open(path) as f:
        raw = yaml.safe_load(f) or {}

    if not isinstance(raw, dict):
        raise ValueError("Device registry root must be a mapping")

    devices: list[dict[str, Any]] = []
    for key, entries in raw.items():
        # Only consider sections like "fitbit_devices", "atmotube_devices", etc.
        if not key.endswith("_devices") or not entries:
            continue

        for d in entries:
            # Validate required fields are present
            if "id" not in d or "type" not in d:
                raise ValueError(f"Malformed device entry in '{key}': {d}")

            # Append each validated device dict into the flattened list
            devices.append(d)

    return devices
