"""Hard rules checked in code before anything is posted (spec: Publisher captions, Guardrails)."""
from __future__ import annotations

import re

# Pictographs, dingbats, flags, variation selector and zero-width joiner.
EMOJI = re.compile("[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF️‍⭐⭕⌀-⏿]")
DASHES = re.compile("[—–]")       # em dash and en dash
HASHTAG = re.compile(r"(?<!\w)#\w+")
IG_CAPTION_MAX = 2200
MAX_HASHTAGS = 5


def caption_problems(caption: str) -> list[str]:
    """Every reason this caption may not be posted. Empty list means it's fine."""
    p = []
    if not caption or not caption.strip():
        return ["caption is empty"]
    if len(caption) > IG_CAPTION_MAX:
        p.append(f"caption is {len(caption)} characters (Instagram max {IG_CAPTION_MAX})")
    if EMOJI.search(caption):
        p.append("caption contains an emoji")
    if DASHES.search(caption):
        p.append("caption contains an em or en dash")
    if re.search(r"link\s+in\s+(my\s+)?bio", caption, re.I):
        p.append('caption says "link in bio"')
    n = len(HASHTAG.findall(caption))
    if n > MAX_HASHTAGS:
        p.append(f"caption has {n} hashtags (max {MAX_HASHTAGS})")
    return p
