"""JTA '3 Pictures' series thumbnails: bright image, heavy outlined gold title, 3-picture strip, JTA mark."""
import math, sys
sys.path.insert(0, "/home/claude/jta-video-agent")
import cairo
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont
from jta_anim import props as P, egypt
from jta_anim.core import outline_fill, rounded_rect, text
from jta_anim.theme import C

W, H = 1280, 720
BLACK = "/usr/share/fonts/opentype/noto/NotoSansCJK-Black.ttc"

def strip(names=("DOMINOES", "DIALS", "PAINTING"), x0=40, y=640, s=0.36, icons=None):
    """Three small framed pictures joined by a gold line, like a level select."""
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, 1920, 1080)
    ctx = cairo.Context(surf)
    k = 1920 / W
    xs = [(x0 + 70 + i * 150) * k for i in range(3)]
    yy = y * k - 40
    ctx.move_to(xs[0], yy); ctx.line_to(xs[2], yy)
    ctx.set_source_rgb(*C["gold"]); ctx.set_line_width(8); ctx.stroke()
    for i, x in enumerate(xs):
        P.picture_frame(ctx, x, yy, P.FRAME_W, P.FRAME_H, lit=0.5, scale=s * 1.0)
        (icons or P.frame_icon)(ctx, i, x, yy, s, 1.0)
        text(ctx, names[i], x, yy + 100 * s * 1.0 + 70, 30, C["papyrus"], spacing=5, shadow=True)
    return Image.frombuffer("RGBA", (1920, 1080), bytes(surf.get_data()), "raw", "BGRA", 0, 1).resize((W, H), Image.LANCZOS)

def title(im, lines, x, y, size, align="left", fill_top=(255, 226, 150), fill_bot=(222, 156, 48)):
    f = ImageFont.truetype(BLACK, size, index=0)
    d = ImageDraw.Draw(im)
    lh = int(size * 1.02)
    mask = Image.new("L", im.size, 0)
    md = ImageDraw.Draw(mask)
    pos = []
    for i, ln in enumerate(lines):
        w = d.textlength(ln, font=f)
        xx = x - w if align == "right" else (x - w / 2 if align == "center" else x)
        pos.append((xx, y + i * lh))
    shadow = Image.new("L", im.size, 0)
    sd = ImageDraw.Draw(shadow)
    for (xx, yy), ln in zip(pos, lines):
        sd.text((xx + 6, yy + 8), ln, font=f, fill=255, stroke_width=14, stroke_fill=255)
    im.paste((0, 0, 0), (0, 0), shadow.filter(ImageFilter.GaussianBlur(10)))
    for (xx, yy), ln in zip(pos, lines):
        d.text((xx, yy), ln, font=f, fill=(35, 20, 8), stroke_width=12, stroke_fill=(35, 20, 8))
        md.text((xx, yy), ln, font=f, fill=255)
    grad = Image.new("RGB", im.size)
    gd = ImageDraw.Draw(grad)
    top, bot = y, y + lh * len(lines)
    for yy in range(H):
        k = min(max((yy - top) / max(bot - top, 1), 0), 1)
        gd.line([(0, yy), (W, yy)], fill=tuple(int(fill_top[c] + (fill_bot[c] - fill_top[c]) * k) for c in range(3)))
    im.paste(grad, (0, 0), mask)

def mark(im, x=24, y=20):
    f = ImageFont.truetype(BLACK, 22, index=0)
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((x, y, x + 300, y + 40), 10, fill=(169, 73, 44))
    d.text((x + 150, y + 20), "JESUS THROUGH ANALOGIES", font=f, fill=(239, 230, 210), anchor="mm")

def tag(im, txt, x, y):
    f = ImageFont.truetype(BLACK, 26, index=0)
    d = ImageDraw.Draw(im)
    w = d.textlength(txt, font=f)
    d.rounded_rectangle((x, y, x + w + 36, y + 46), 10, fill=(239, 230, 210), outline=(35, 20, 8), width=4)
    d.text((x + 18 + w / 2, y + 23), txt, font=f, fill=(35, 20, 8), anchor="mm")

def photo(src, crop=None, bright=1.3, contrast=1.15, sat=1.15, shade=None):
    im = Image.open(src).convert("RGB")
    if crop:
        im = im.crop(crop)
    im = im.resize((W, H), Image.LANCZOS)
    im = ImageEnhance.Brightness(im).enhance(bright)
    im = ImageEnhance.Contrast(im).enhance(contrast)
    im = ImageEnhance.Color(im).enhance(sat)
    if shade:   # soft dark band behind the title: (x0, x1) fraction of width
        g = Image.new("L", (W, H), 0)
        gd = ImageDraw.Draw(g)
        a, b = shade
        for x in range(W):
            u = x / W
            k = 1 - min(abs(u - (a + b) / 2) / ((b - a) / 2 + 0.15), 1)
            gd.line([(x, 0), (x, H)], fill=int(150 * k))
        im.paste((10, 6, 2), (0, 0), g)
    # darken the bottom so the strip reads
    g = Image.new("L", (W, H), 0)
    gd = ImageDraw.Draw(g)
    for y in range(H):
        gd.line([(0, y), (W, y)], fill=int(170 * max(0, (y - 480) / 240)))
    im.paste((10, 6, 2), (0, 0), g)
    return im

def finish(im, out):
    im = im.convert("RGB")
    im.save(out, quality=93)
