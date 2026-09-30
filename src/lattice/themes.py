"""Built-in themes: CSS file, Pygments style and palette shared with components."""
from __future__ import annotations

THEMES = {
    "default": {
        "css": "default.css",
        "pygments": "friendly",
        "palette": {
            "ink": "#1d2433", "muted": "#5d6778", "accent": "#0b6e7f", "grid": "#e3e7ee",
            "series": ["#0b6e7f", "#c8741a", "#6a4fb3", "#2f8f4e", "#b23a48", "#5d6778"],
        },
    },
    "dark": {
        "css": "dark.css",
        "pygments": "one-dark",
        "palette": {
            "ink": "#e7eaf0", "muted": "#9aa4b5", "accent": "#5cc8d6", "grid": "#343c4d",
            "series": ["#5cc8d6", "#f2b544", "#b69cff", "#6fcf8a", "#ff7a85", "#9aa4b5"],
        },
    },
}


def get_theme(name: str) -> dict:
    return THEMES.get(name, THEMES["default"])
