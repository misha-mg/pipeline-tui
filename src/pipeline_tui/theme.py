"""The app's colors: gruvbox, softened, with yellow for frames and pink for accents.

The second color is aqua: the chart draws "nothing to build" in it, and pink sat too close to the
red of "blocked" to tell them apart.
"""

from textual.theme import Theme

GRUVBOX_SOFT = Theme(
    name="gruvbox-soft",
    primary="#d8a657",
    secondary="#7daea3",
    accent="#d3869b",
    warning="#e78a4e",
    error="#ea6962",
    success="#a9b665",
    foreground="#ebdbb2",
    background="#282828",
    surface="#32302f",
    panel="#45403d",
    dark=True,
)
