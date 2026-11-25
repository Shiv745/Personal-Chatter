"""Thread-safe configuration manager for PulseAI Agent."""
import json
import threading
from pathlib import Path
from typing import Any, Dict

CONFIG_PATH = Path("config.json")
_LOCK = threading.RLock()

DEFAULT_CONFIG: Dict[str, Any] = {
    "gemini_api_key": "YOUR_GEMINI_API_KEY_HERE",
    "primary_model": "gemini-3.5-flash",
    "propose_model": "gemini-3.5-flash",
    "fallback_model": "gemini-3.5-flash",
    "custom_base_url": "",
    "your_name": "Shivendra",
    "default_mode": "autopilot",
    "server_port": 8765,
    "browser": {
        "headless": False,
        "profile_dir": "browser_profile",
        "use_installed_chrome": True,
    },
    "enabled_platforms": {
        "instagram": True,
        "whatsapp": True,
        "linkedin": True,
    },
    "whitelist": {
        "instagram": [],
        "whatsapp": [],
        "linkedin": [],
    },
    "delays": {
        "instagram": {
            "poll_min_sec": 22,
            "poll_max_sec": 45,
            "read_min_sec": 4,
            "read_max_sec": 12,
            "type_min_ms": 75,
            "type_max_ms": 185,
            "max_replies_per_hour": 18,
        },
        "whatsapp": {
            "poll_min_sec": 5,
            "poll_max_sec": 8,
            "read_min_sec": 2,
            "read_max_sec": 4,
            "type_min_ms": 60,
            "type_max_ms": 100,
            "max_replies_per_hour": 12,
        },
        "linkedin": {
            "poll_min_sec": 35,
            "poll_max_sec": 75,
            "read_min_sec": 5,
            "read_max_sec": 14,
            "type_min_ms": 75,
            "type_max_ms": 190,
            "max_replies_per_hour": 12,
        },
    },
}


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    result = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(result.get(k), dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def load_config(path: Path = CONFIG_PATH) -> Dict[str, Any]:
    with _LOCK:
        if not path.exists():
            save_config(DEFAULT_CONFIG, path)
            return json.loads(json.dumps(DEFAULT_CONFIG))
        with path.open("r", encoding="utf-8") as f:
            raw = json.load(f)
        return _deep_merge(DEFAULT_CONFIG, raw)


def save_config(cfg: Dict[str, Any], path: Path = CONFIG_PATH) -> None:
    with _LOCK:
        with path.open("w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
