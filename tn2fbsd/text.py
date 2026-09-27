"""Access to the MIGRATION.md text kept in data/messages.toml.

Each message is a str.format template; callers pass any placeholders.
"""
import tomllib
from pathlib import Path

_MESSAGES = tomllib.loads(
    (Path(__file__).resolve().parent / "data" / "messages.toml").read_text(encoding="utf8")
)


def text(section, key, **fields):
    """Return the message, filled with the given placeholder values."""
    template = _MESSAGES[section][key]
    return template.format(**fields) if fields else template
