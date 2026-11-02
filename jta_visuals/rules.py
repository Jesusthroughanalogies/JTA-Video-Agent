"""Locked JTA visual rules (approved by Matt, 2 Nov 2026).

Source of truth for the agent. Section 5 of the system prompt explains each value.
"""

# --- Jesus character -------------------------------------------------------
JESUS_ELEMENT_ID = "163a3147-288b-48fc-b021-30f6cc9b7d61"  # Higgsfield element "JTA-Jesus"
JESUS_MASTER_JOB = "10260372-5958-42e8-900d-f51448c2d4f5"
JESUS_TOKEN = f"<<<{JESUS_ELEMENT_ID}>>>"
JESUS_RULES = (
    "Exactly the same clothes and hair as the reference, hood down. "
    "Seen from behind; his face is never visible and he never turns toward camera."
)

# --- Models and costs (measured 2 Nov 2026) ---------------------------------
VIDEO_MODEL = "kling3_0"
VIDEO_PARAMS = {"mode": "pro", "aspect_ratio": "16:9", "duration": 5, "sound": "off"}
FRAME_MODEL = "nano_banana_pro"
FRAME_PARAMS = {"aspect_ratio": "16:9"}

CREDITS_PER_CLIP = 8.75   # Kling 3.0 pro, 5 s, 1080p, sound off
CREDITS_PER_FRAME = 2.0   # Nano Banana Pro start frame
REDO_ALLOWANCE = 0.30     # added on top of the planned generations
EPISODE_CREDIT_CAP = 1200

# --- Prompt pieces -----------------------------------------------------------
LENS = "35mm cinematic, shallow depth of field."

ANCIENT_ENDING = (
    "Only first-century materials: stone, mud plaster, timber, wool, linen, leather, clay, bronze, iron. "
    "No modern objects: no glass windows, no electric lights, no wires, no poles, no antennas, "
    "no vehicles, no plastic, no modern clothing, no tiled roofs, no towers, no chimneys, "
    "no text, no lettering, no numbers."
)
NATURE_ENDING = "No people, no buildings, no boats unless described, no text, no lettering."

OTHER_PEOPLE_DRESS = (
    "Everyone else wears plain grey, blue, striped or patterned wool robes, "
    "never an off-white tunic with a brown mantle."
)

# Words the scene description may not contain (the negative ending is exempt).
BANNED_WORDS = [
    "car", "cars", "truck", "road sign", "tarmac", "asphalt", "street light", "streetlight",
    "electric", "electricity", "bulb", "neon", "lamp post", "power line", "wire", "wires",
    "cable", "antenna", "phone", "screen", "monitor", "laptop", "computer", "switch",
    "plastic", "glass window", "window pane", "skyscraper", "skyline", "city lights",
    "observatory", "telescope", "gallery", "museum", "office", "bedroom", " bed ", "sofa",
    "couch", "coffee", "mug", "book", "bible", "paper", "newspaper", "pen ", "clock", "watch",
    "glasses", "sunglasses", "jeans", "t-shirt", "hoodie", "sneakers", "zip", "candle",
    "control panel", "gauge", "vintage", "tiled roof", "church", "tower", "chimney",
    "oil paint", "canvas",
]

# --- The grade, applied in the edit to every AI clip -------------------------
GRADE_FILTER = (
    "eq=contrast=1.08:saturation=0.9:gamma=0.97,"
    "colorbalance=rs=0.04:gs=0.01:bs=-0.04:rm=0.02:bm=-0.02:rh=0.03:bh=-0.05,"
    "vignette=angle=PI/5,"
    "noise=alls=6:allf=t+u"
)
