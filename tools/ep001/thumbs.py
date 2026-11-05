from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageEnhance
F = "/usr/share/fonts/truetype/dejavu/DejaVuSerifCondensed-Bold.ttf"
GOLD_T, GOLD_B = (246, 214, 140), (196, 140, 52)

def gold_text(base, lines, box, size, align="right"):
    x0, y0, x1 = box
    f = ImageFont.truetype(F, size)
    lh = int(size * 1.08)
    W, H = base.size
    mask = Image.new("L", base.size, 0)
    d = ImageDraw.Draw(mask)
    y = y0
    for ln in lines:
        w = d.textlength(ln, font=f)
        x = x1 - w if align == "right" else (x0 if align == "left" else (x0 + x1 - w) / 2)
        d.text((x, y), ln, font=f, fill=255)
        y += lh
    # shadow / dark glow
    sh = mask.filter(ImageFilter.GaussianBlur(14))
    base.paste((0, 0, 0), (0, 0), sh.point(lambda v: min(255, int(v * 1.6))))
    stroke = mask.filter(ImageFilter.MaxFilter(7))
    base.paste((30, 18, 8), (0, 0), stroke)
    grad = Image.new("RGB", base.size)
    gd = ImageDraw.Draw(grad)
    for yy in range(H):
        k = min(max((yy - y0) / max(lh * len(lines), 1), 0), 1)
        gd.line([(0, yy), (W, yy)], fill=tuple(int(GOLD_T[i] + (GOLD_B[i] - GOLD_T[i]) * k) for i in range(3)))
    base.paste(grad, (0, 0), mask)

def make(src, out, lines, box, size, align="right", darken_side="right", crop=None, bright=1.0):
    im = Image.open(src).convert("RGB")
    if crop:
        im = im.crop(crop)
    im = im.resize((1280, 720), Image.LANCZOS)
    im = ImageEnhance.Contrast(im).enhance(1.12)
    im = ImageEnhance.Brightness(im).enhance(bright)
    # darken the text side so the words pop on a phone
    g = Image.new("L", (1280, 720))
    gd = ImageDraw.Draw(g)
    for x in range(1280):
        k = x / 1279 if darken_side == "right" else 1 - x / 1279 if darken_side == "left" else 0.5
        gd.line([(x, 0), (x, 720)], fill=int(200 * max(0, k - 0.25) / 0.75))
    im.paste((0, 0, 0), (0, 0), g)
    gold_text(im, lines, box, size, align)
    im.save(out, quality=92)

make("cliff.png", "2_who_made_all_this.jpg", ["WHO MADE", "ALL THIS?"], (0, 150, 1240), 140, darken_side="right")
make("jesus.png", "3_three_clues.jpg", ["3 CLUES", "GOD IS REAL"], (40, 60, 1280), 120, align="left", darken_side="left")
make("fresco.png", "4_who_painted_this.jpg", ["WHO PAINTED", "THIS?"], (0, 360, 1240), 120, darken_side="right", crop=(0, 140, 1600, 1040))
make("dials2.png", "5_who_set_the_dials.jpg", ["WHO SET", "THE DIALS?"], (40, 80, 1280), 130, align="left", darken_side="left")
make("cliff.png", "2_who_made_all_this.jpg", ["WHO MADE ALL THIS?"], (0, 30, 1280), 104, align="center", darken_side="none", bright=0.95)
