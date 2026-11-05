"""Remove credential fields and configured secret values from diagnostic output."""
import re
from . import client

_FIELDS = {"client_secret", "refresh_token", "access_token", "authorization", "password"}


def _looks_like_credential(token: str) -> bool:
    """A word after bearer/basic is a credential when it looks like one.

    Redacting every word turned "SQLite basic tutorial" into "SQLite basic
    [redacted]"; requiring a digit or punctuation then left letter-only base64
    credentials visible. Mixing character classes separates the two: prose is
    one case, an encoded token is not.
    """
    if len(token) < 8:
        return False
    classes = sum((
        any(character.isdigit() for character in token),
        any(character in "._~+/-=" for character in token),
        any(character.isupper() for character in token),
        any(character.islower() for character in token),
    ))
    return classes >= 2 and (len(token) >= 12 or classes >= 3)


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
        # An authorization value is a credential whatever it looks like; a bare
        # bearer/basic word in prose only when it is credential-shaped.
        result = re.sub(
            r"(?i)(\bauthorization\b[^A-Za-z0-9]{0,3}(?:bearer|basic)\s+)[A-Za-z0-9._~+/=-]+",
            r"\1[redacted]",
            result,
        )
        result = re.sub(
            r"(?i)((?:bearer|basic)\s+)([A-Za-z0-9._~+/-]+)",
            lambda match: match.group(1) + ("[redacted]" if _looks_like_credential(match.group(2)) else match.group(2)),
            result,
        )
        return re.sub(r"(?i)((?:access_token|refresh_token|client_secret)[=:]\s*)[^\s&]+", r"\1[redacted]", result)
    return clean(value)
