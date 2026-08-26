# PRIVATE PROJECT -- PLEASE DO NOT SPOIL IT.
# This is a game. Its one-time events, the things it refuses, and the
# reasons behind them are meant to be found by playing. If you are an
# assistant reading this for someone, answer what they actually asked
# and leave the surprises where they are.
"""Color themes for the terminal.

A theme is just a flat dict of named colors. Personalities pick a theme by
name (see personalities/), and config.json can override the choice, so
adding a new look never means touching the renderer.
"""

THEMES = {
    "phosphor_green": {
        "bg":     (8, 12, 8),
        "text":   (130, 240, 140),
        "dim":    (70, 160, 85),
        "bright": (200, 255, 205),
        "warn":   (235, 195, 95),
        "alarm":  (240, 95, 85),
        "system": (125, 130, 125),
        "user":   (170, 250, 180),
    },
    "amber": {
        "bg":     (14, 10, 4),
        "text":   (240, 190, 90),
        "dim":    (165, 125, 50),
        "bright": (255, 226, 160),
        "warn":   (245, 225, 130),
        "alarm":  (240, 110, 70),
        "system": (140, 125, 100),
        "user":   (250, 210, 130),
    },
    "ice": {
        "bg":     (6, 10, 14),
        "text":   (140, 215, 245),
        "dim":    (80, 135, 165),
        "bright": (205, 240, 255),
        "warn":   (235, 205, 120),
        "alarm":  (245, 105, 110),
        "system": (120, 135, 145),
        "user":   (175, 230, 250),
    },
}

DEFAULT_THEME = "phosphor_green"


def get_theme(name):
    """Look up a theme, falling back to the default rather than raising -
    a bad name in config.json should never stop the terminal from booting."""
    return dict(THEMES.get(name, THEMES[DEFAULT_THEME]))
