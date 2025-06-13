"""Helper utilities"""
import re
from typing import Dict, Any, List


def sanitize_filename(name: str) -> str:
    """Sanitize string for use as filename"""
    return re.sub(r'[<>:"/\\|?*]', '_', name)


def deep_get(dictionary: Dict, keys: str, default: Any = None) -> Any:
    """Get nested dictionary value using dot notation"""
    keys_list = keys.split('.')
    value = dictionary

    for key in keys_list:
        if isinstance(value, dict):
            value = value.get(key, default)
        else:
            return default

    return value


def interpolate_string(template: str, data: Dict) -> str:
    """Interpolate variables in string template"""
    for key, value in data.items():
        template = template.replace(f"{{{key}}}", str(value))
        template = template.replace(f"${{{key}}}", str(value))
    return template