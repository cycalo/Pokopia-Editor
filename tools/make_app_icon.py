"""Builds the app icon: the in-game Ditto portrait on a rounded island badge.

Usage:  py tools\\make_app_icon.py      -> data\\app.ico (16-256 px) and data\\app.png (512 px)

Needs Pillow and the icons fetched by tools\\fetch_icons.py.
"""
import os, struct, sys
from PIL import Image, ImageDraw, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, 'data')
DITTO = 78          # villager record index of Ditto
MASTER = 1024


def ditto_sprite():
    with open(os.path.join(DATA, 'villager_portrait.bin'), 'rb') as f:
        raw = f.read()
    n = struct.unpack_from('<H', raw, DITTO * 2)[0]
    im = Image.open(os.path.join(DATA, 'icons', 'villagers', f'villager_{n:04}.png')).convert('RGBA')
    return im.crop(im.getchannel('A').getbbox())


def lerp(a, b, t):
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def badge(size=MASTER):
    """Rounded square: sky gradient, sea, a grassy island, white rim. Drawn big, scaled down later."""
    S = size
    r = int(S * 0.23)
    sky = Image.new('RGBA', (S, S))
    d = ImageDraw.Draw(sky)
    top, bottom = (88, 190, 245), (190, 236, 255)
    for y in range(S):
        d.line([(0, y), (S, y)], fill=lerp(top, bottom, y / S) + (255,))
    # soft sun glow
    glow = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse((S * 0.62, S * 0.08, S * 0.92, S * 0.38), fill=(255, 250, 215, 120))
    sky.alpha_composite(glow.filter(ImageFilter.GaussianBlur(S * 0.05)))
    # clouds
    cl = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    cd = ImageDraw.Draw(cl)
    for cx, cy, w in ((0.22, 0.24, 0.20), (0.33, 0.21, 0.16), (0.70, 0.36, 0.14)):
        cd.ellipse((S * (cx - w / 2), S * (cy - w / 4), S * (cx + w / 2), S * (cy + w / 4)), fill=(255, 255, 255, 235))
    sky.alpha_composite(cl.filter(ImageFilter.GaussianBlur(S * 0.004)))
    # sea band
    sea = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    sd = ImageDraw.Draw(sea)
    for y in range(int(S * 0.60), S):
        t = (y - S * 0.60) / (S * 0.40)
        sd.line([(0, y), (S, y)], fill=lerp((64, 170, 228), (34, 120, 196), t) + (255,))
    sky.alpha_composite(sea)
    # island: sand rim, then grass hill
    isl = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    idr = ImageDraw.Draw(isl)
    idr.ellipse((S * 0.08, S * 0.55, S * 0.92, S * 0.98), fill=(245, 222, 160, 255))
    idr.ellipse((S * 0.12, S * 0.50, S * 0.88, S * 0.92), fill=(112, 196, 92, 255))
    idr.ellipse((S * 0.20, S * 0.52, S * 0.70, S * 0.70), fill=(140, 214, 112, 255))  # highlight
    sky.alpha_composite(isl.filter(ImageFilter.GaussianBlur(S * 0.002)))
    # round the corners and add a white rim
    mask = Image.new('L', (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, S - 1, S - 1), r, fill=255)
    out = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    out.paste(sky, (0, 0), mask)
    rim = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    w = max(2, int(S * 0.035))
    ImageDraw.Draw(rim).rounded_rectangle((0, 0, S - 1, S - 1), r, outline=(255, 255, 255, 255), width=w)
    out.alpha_composite(rim)
    return out


def upscale(sprite, tw, th):
    """Resize the small sprite (Pillow resizes RGBA premultiplied, so no dark fringes); sharpen a
    little when it is enlarged so the outline does not go mushy."""
    sp = sprite.resize((tw, th), Image.LANCZOS)
    if tw > sprite.width * 1.5:
        sp = sp.filter(ImageFilter.UnsharpMask(radius=max(1, tw / sprite.width * 0.5), percent=70, threshold=2))
    return sp


def compose(size, master, sprite):
    im = master.resize((size, size), Image.LANCZOS)
    # Ditto sits on the hill, about 62% of the badge wide
    tw = round(size * 0.58)
    th = round(sprite.height * tw / sprite.width)
    sp = upscale(sprite, tw, th)
    x, y = (size - tw) // 2, round(size * 0.74) - th
    shadow = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).ellipse((x + tw * 0.12, y + th * 0.86, x + tw * 0.88, y + th * 1.04), fill=(20, 70, 30, 110))
    im.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(max(1, size * 0.012))))
    im.alpha_composite(sp, (x, y))
    return im


def main():
    sprite = ditto_sprite()
    master = badge()
    sizes = [16, 20, 24, 32, 40, 48, 64, 96, 128, 256]
    frames = [compose(s, master, sprite) for s in sizes]
    ico = os.path.join(DATA, 'app.ico')
    frames[-1].save(ico, sizes=[(s, s) for s in sizes], append_images=frames[:-1])
    compose(512, master, sprite).save(os.path.join(DATA, 'app.png'))
    print('Wrote', ico, 'and app.png')


if __name__ == '__main__':
    sys.exit(main())
