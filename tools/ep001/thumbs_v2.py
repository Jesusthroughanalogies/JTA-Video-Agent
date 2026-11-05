import sys; sys.path.insert(0, "/tmp/ep1thumb/v2")
from series import *
from PIL import ImageFilter, ImageEnhance, ImageDraw
import cairo
from jta_anim import egypt, props as P

# 1. The dials chamber (old title covered by a darker band)
src = Image.open("/tmp/thumb/A.png").convert("RGB")
dark = ImageEnhance.Brightness(src.filter(ImageFilter.GaussianBlur(30))).enhance(0.3)
m = Image.new("L", src.size, 0)
ImageDraw.Draw(m).rounded_rectangle((740, 170, 1344, 470), 40, fill=255)
src = Image.composite(dark, src, m.filter(ImageFilter.GaussianBlur(45)))
src.save("/tmp/ep1thumb/v2/A_clean.png")
im = photo("/tmp/ep1thumb/v2/A_clean.png", bright=1.25, shade=(0.55, 1.0))
title(im, ["IS THERE", "A GOD?"], 1245, 150, 150, align="right")
im.alpha_composite if False else None
im = im.convert("RGBA"); im.alpha_composite(strip()); mark(im); finish(im, "1_is_there_a_god.jpg")

# 2. The cliff and the stars
im = photo("/tmp/ep1thumb/cliff.png", bright=1.45, shade=(0.0, 0.35)).convert("RGBA")
title(im, ["WHO", "MADE", "ALL THIS?"], 40, 110, 112)
im.alpha_composite(strip(x0=820)); mark(im); finish(im, "2_who_made_all_this.jpg")

# 3. Jesus in the market
im = photo("/tmp/ep1thumb/jesus.png", bright=1.15, shade=(0.02, 0.45)).convert("RGBA")
title(im, ["3 CLUES", "GOD IS", "REAL"], 110, 95, 118)
im.alpha_composite(strip(x0=90)); mark(im, 110, 24); finish(im, "3_three_clues.jpg")

# 4. Fully illustrated: the three pictures in the temple frame
surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, 1920, 1080)
ctx = cairo.Context(surf)
egypt.background(ctx)
for k in range(3):
    x = 380 + k * 580
    P.picture_frame(ctx, x, 690, P.FRAME_W, P.FRAME_H, lit=0.8, scale=1.5)
    P.frame_icon(ctx, k, x, 690, 1.5, 1.0)
im = Image.frombuffer("RGBA", (1920, 1080), bytes(surf.get_data()), "raw", "BGRA", 0, 1).resize((W, H), Image.LANCZOS)
im = ImageEnhance.Contrast(im.convert("RGB")).enhance(1.1).convert("RGBA")
title(im, ["IS THERE A GOD?"], W / 2, 60, 118, align="center")
tag(im, "3 PICTURES THAT EXPLAIN IT", 440, 210)
mark(im, 24, 650); finish(im, "4_illustrated.jpg")

# 5. The fresco (painting picture), bright
im = photo("/tmp/ep1thumb/fresco.png", crop=(0, 140, 1600, 1040), bright=1.3, shade=(0.0, 0.3)).convert("RGBA")
title(im, ["WHO", "PAINTED", "THIS?"], 40, 110, 116)
im.alpha_composite(strip(x0=820)); mark(im); finish(im, "5_who_painted_this.jpg")

from PIL import Image as I
fs = ["1_is_there_a_god", "2_who_made_all_this", "3_three_clues", "4_illustrated", "5_who_painted_this"]
sheet = I.new("RGB", (1280, 1080), (20, 14, 8))
for i, f in enumerate(fs):
    sheet.paste(I.open(f + ".jpg").resize((640, 360)), ((i % 2) * 640, (i // 2) * 360))
sheet.save("JTA_Ep1_thumbnail_options_v2.jpg")
