"""Remove credential fields and configured secret values from diagnostic output."""
import re
from . import client

_FIELDS = {"client_secret", "refresh_token", "access_token", "authorization", "password"}


def safe(value):
    try:
        records = (client.load_config(), client.load_token())
    except (RuntimeError, OSError, ValueError):
        records = ()
    secrets = [record[key] for record in records for key in _FIELDS if isinstance(record.get(key), str) and record[key]]
    def clean(item):
        if isinstance(item, dict):
            return {key: ("[redacted]" if str(key).lower() in _FIELDS else clean(part)) for key, part in item.items()}
        if isinstance(item, (list, tuple)):
            return [clean(part) for part in item]
        if not isinstance(item, str):
            return item
        result = item
        for secret in secrets:
            if len(secret) >= 6:
                result = result.replace(secret, "[redacted]")
            elif result == secret:
                result = "[redacted]"
        result = re.sub(
            r"(?i)((?:bearer|basic)\s+)(?=[A-Za-z0-9._~+/-]{8,})(?=[A-Za-z0-9._~+/-]*[0-9._~+/-])[A-Za-z0-9._~+/-]+",
            r"\1[redacted]",
            result,
        )
        return re.sub(r"(?i)((?:access_token|refresh_token|client_secret)[=:]\s*)[^\s&]+", r"\1[redacted]", result)
    return clean(value)
