"""Read the active Omarchy palette with a self-contained ATLAS fallback."""

from __future__ import annotations

import os
from pathlib import Path
import re
import sys
import tomllib

FALLBACK = {
    "accent": "#ff5a12",
    "muted": "#3a342c",
    "background": "#100e0c",
    "foreground": "#d6cfc4",
    "dark_foreground": "#6e675c",
    "light_foreground": "#c4b8a8",
    "bright_foreground": "#f2ebe0",
    "red": "#c22e16",
    "yellow": "#f0a202",
    "orange": "#e24a0f",
    "green": "#8a9a4a",
    "cyan": "#6f9a92",
    "blue": "#6a8aa0",
    "magenta": "#a03c2a",
    "brown": "#6a3a22",
    "bright_red": "#e84528",
    "bright_yellow": "#ffb020",
    "bright_green": "#a8b85c",
    "bright_cyan": "#8fb8b0",
    "bright_blue": "#8aa8bc",
    "bright_magenta": "#c45438",
}
RESET = "\033[0m"
ROLES = {
    "address": "cyan",
    "success": "green",
    "warning": "yellow",
    "error": "bright_red",
    "secondary": "dark_foreground",
    "heading": "accent",
}
HEX = re.compile(r"#[0-9a-fA-F]{6}")


def load_theme(home: str | os.PathLike[str] | None = None) -> dict[str, str]:
    """Return valid literal colors from the active theme, or fallback values."""
    colors = dict(FALLBACK)
    theme = Path(home or Path.home()) / ".local/state/omarchy/current/theme/colors.toml"
    try:
        raw = tomllib.loads(theme.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return colors
    for key, value in raw.items():
        if isinstance(value, str) and HEX.fullmatch(value):
            colors[key] = value
    return colors


def fg(colors: dict[str, str], role: str) -> str:
    value = colors.get(ROLES.get(role, role), FALLBACK["foreground"])
    if not HEX.fullmatch(value):
        value = FALLBACK["foreground"]
    red, green, blue = (int(value[index:index + 2], 16) for index in (1, 3, 5))
    return f"\033[38;2;{red};{green};{blue}m"


def want_color(mode: str = "auto", stream=None) -> bool:
    if os.environ.get("NO_COLOR") or mode == "never":
        return False
    if mode == "always":
        return True
    return (stream or sys.stdout).isatty() and os.environ.get("TERM") != "dumb"
