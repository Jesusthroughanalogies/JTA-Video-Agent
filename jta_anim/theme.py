"""JTA long-form animation theme (system prompt 5.5).

The short-form reels' layout and motion, recoloured in ancient Middle East earth colours,
set against an ancient Egyptian environment. Change the look here and only here.
"""

W, H, FPS = 1920, 1080, 30


def hexrgb(h: str) -> tuple[float, float, float]:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))  # type: ignore[return-value]


PAL = {
    # system prompt 5.5 palette
    "papyrus": "#E9DCC0",
    "papyrus_dark": "#D9C49A",
    "ink": "#3A2A1D",
    "gold": "#B8862F",
    "terracotta": "#A9492C",
    "olive": "#6E7244",
    "indigo": "#34506E",
    "bronze": "#8C5E2E",
    "night_bg": "#211812",
    "night_text": "#E6D3AC",
    # environment (ancient Egypt, earth tones)
    "sky_top": "#EFE3C8",
    "sky_low": "#E3CFA4",
    "sun": "#D9A441",
    "dune_far": "#D8C08F",
    "dune_mid": "#CBAE78",
    "ground": "#C2A06A",
    "stone_lit": "#D7BE8C",
    "stone_shade": "#B39260",
    "column": "#DCC8A0",
    # people (must match the AI footage, system prompt 5.2 and 5.5)
    "skin": "#B98A64",
    "jesus_tunic": "#EDE3CF",
    "jesus_mantle": "#4A3527",
    "jesus_hair": "#3B2A20",
    "sandal": "#7A5233",
    "rope": "#A8875A",
    "seeker_robe": "#8B877E",
    "seeker_robe_shade": "#76726A",
    "seeker_hair": "#2E241C",
    # props
    "limestone": "#EFE6D2",
    "bronze_face": "#C99A5B",
    "bronze_light": "#E2B877",
}
C = {k: hexrgb(v) for k, v in PAL.items()}

FONT = "IM FELL DW Pica"
OUTLINE = 5.0          # thick outlines, as in the reels' drawn style
GRAIN_ALPHA = 0.07     # paper grain over every frame
CAPTION_Y = 930        # caption baseline (lower third, clear of the content)
CAPTION_MAX_W = 1000   # narrow centred column
