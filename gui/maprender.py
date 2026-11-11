"""Island map layers (Pillow only, runs in a worker thread) and fast composition of the visible layers.

Layers are computed once per island; switching relief / contours / objects only re-composes them with
Pillow's C operations, which takes a fraction of a second.
"""
from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter

import pokopia_extras as px
import pokopia_items as pi


def _lerp(a, b, t):
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def _ramp(stops, n=256):
    """[(position, (r,g,b)), ...] -> list of n colours."""
    out = []
    for v in range(n):
        for (p0, c0), (p1, c1) in zip(stops, stops[1:]):
            if p0 <= v <= p1:
                out.append(_lerp(c0, c1, (v - p0) / max(1, p1 - p0)))
                break
        else:
            out.append(stops[-1][1] if v > stops[-1][0] else stops[0][1])
    return out


SEA = px.StageMap.SEA_LEVEL
# land colour by height (blocks): beach, meadow, forest, highland, rock, snow
HEIGHT_RAMP = _ramp([(0, (176, 160, 118)), (SEA, (226, 210, 156)), (SEA + 2, (186, 206, 120)), (SEA + 7, (132, 186, 90)),
                     (SEA + 15, (100, 164, 76)), (SEA + 23, (80, 138, 66)), (SEA + 29, (128, 136, 88)),
                     (SEA + 35, (146, 140, 124)), (SEA + 43, (182, 178, 168)), (SEA + 60, (236, 238, 242)),
                     (255, (236, 238, 242))])
# water colour by closeness to land (255 = right at the shore, 0 = open sea)
WATER_RAMP = _ramp([(0, (30, 96, 170)), (40, (38, 116, 188)), (110, (56, 152, 210)), (190, (92, 192, 222)),
                    (255, (136, 220, 228))])


def block_color(bid):
    """Stable muted colour per block id so different materials stay distinguishable."""
    h = (bid * 2654435761) & 0xFFFFFFFF
    return 96 + (h & 79), 104 + (h >> 8 & 79), 72 + (h >> 16 & 63)


def _lut_rgb(gray, ramp):
    lr = [c[0] for c in ramp]
    lg = [c[1] for c in ramp]
    lb = [c[2] for c in ramp]
    return Image.merge('RGB', (gray.point(lr), gray.point(lg), gray.point(lb)))


def build_layers(m):
    """Everything the map page needs for one decoded StageMap."""
    W, H = m.width, m.height
    hts = Image.frombytes('L', (W, H), bytes(m.heights))
    nodata = hts.point(lambda v: 255 if v == m.NO_DATA else 0)
    depth = Image.frombytes('L', (W, H), bytes(m.depth))
    water = depth.point(lambda v: 255 if v else 0)
    land = ImageChops.subtract(ImageChops.invert(water), nodata)
    # material colours blended with a height ramp
    table = [bytes(block_color(b)) for b in range(2048)]
    ids = m.ids
    mat = Image.frombytes('RGB', (W, H), b''.join(map(table.__getitem__, ids)))
    tint = _lut_rgb(hts, HEIGHT_RAMP)
    base = Image.blend(tint, mat, 0.38)
    # hillshade, light from the north-west
    a = ImageChops.offset(hts, -1, 0)
    b = ImageChops.offset(hts, 1, 0)
    cimg = ImageChops.offset(hts, 0, -1)
    d = ImageChops.offset(hts, 0, 1)
    s1 = ImageChops.subtract(b, a, 1.0, 128)    # 128 - dx
    s2 = ImageChops.subtract(d, cimg, 1.0, 128)  # 128 - dz
    shade = ImageChops.add(s1, s2, 1.0, -128).point(lambda v: max(0, min(255, round(150 + (v - 128) * 26))))
    shade = ImageChops.composite(Image.new('L', (W, H), 150), shade, ImageChops.invert(land))
    # contour lines every 4 blocks
    q = hts.point(lambda v: 255 if v == m.NO_DATA else v // 4 * 4)
    e1 = ImageChops.difference(q, ImageChops.offset(q, 1, 0))
    e2 = ImageChops.difference(q, ImageChops.offset(q, 0, 1))
    contour = ImageChops.lighter(e1, e2).point(lambda v: 255 if v else 0)
    contour = ImageChops.multiply(contour, land)
    # shoreline: land next to water and water next to land
    shore_land = ImageChops.multiply(water.filter(ImageFilter.MaxFilter(3)), land)
    foam = ImageChops.multiply(land.filter(ImageFilter.MaxFilter(3)), water)
    near = land.filter(ImageFilter.BoxBlur(6)).filter(ImageFilter.GaussianBlur(10)).point(lambda v: min(255, v * 3))
    wcol = _lut_rgb(near, WATER_RAMP)
    wcol = Image.composite(Image.blend(wcol, Image.new('RGB', (W, H), (236, 248, 250)), 0.55), wcol, foam)
    base = Image.composite(Image.blend(base, Image.new('RGB', (W, H), (226, 212, 160)), 0.45), base, shore_land)
    # placed objects, tinted by item category
    objs = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    dr = ImageDraw.Draw(objs)
    for var, item, x0, z0, x1, z1, y, hh, drn in m.placed:
        col = pi.CAT_COLOR.get(pi.category(item), '#9aa5b1') if item else '#9aa5b1'
        r, g, bb = int(col[1:3], 16), int(col[3:5], 16), int(col[5:7], 16)
        dr.rectangle((x0 - m.x0, z0 - m.z0, x1 - m.x0, z1 - m.z0), fill=(r, g, bb, 175))
    return dict(base=base, shade=shade, contour=contour, water=water, wcol=wcol, nodata=nodata, objects=objs)


def compose(layers, bg, relief=True, contours=False, objects=True):
    base = layers['base']
    if relief:
        bright = ImageEnhance.Brightness(base).enhance(1.32)
        dark = ImageEnhance.Brightness(base).enhance(0.52)
        base = Image.composite(bright, dark, layers['shade'])
    if contours:
        base = Image.composite(ImageEnhance.Brightness(base).enhance(0.72), base, layers['contour'])
    img = Image.composite(layers['wcol'], base, layers['water'])
    img = Image.composite(Image.new('RGB', img.size, bg), img, layers['nodata'])
    if objects:
        img = img.convert('RGBA')
        img.alpha_composite(layers['objects'])
        img = img.convert('RGB')
    return img


class IslandData:
    """A decoded island: the StageMap, its layers, a spatial index of placed objects and composed images."""

    def __init__(self, m):
        self.m = m
        self.layers = build_layers(m)
        self.composed = {}
        self.buckets = {}
        for n, p in enumerate(m.placed):
            for bx in range((p[2] - m.x0) // 32, (p[4] - m.x0) // 32 + 1):
                for bz in range((p[3] - m.z0) // 32, (p[5] - m.z0) // 32 + 1):
                    self.buckets.setdefault((bx, bz), []).append(n)
        from collections import Counter
        self.top = Counter(p[1] for p in m.placed if p[1]).most_common(8)

    def parts_in(self, x0, z0, x1, z1):
        """Placed objects overlapping a pixel rectangle."""
        seen = set()
        for bx in range(int(x0) // 32, int(x1) // 32 + 1):
            for bz in range(int(z0) // 32, int(z1) // 32 + 1):
                for n in self.buckets.get((bx, bz), ()):
                    if n not in seen:
                        seen.add(n)
                        yield self.m.placed[n]

    def part_at(self, ix, iz):
        m = self.m
        hits = [p for p in self.parts_in(ix, iz, ix, iz)
                if p[2] - m.x0 <= ix <= p[4] - m.x0 and p[3] - m.z0 <= iz <= p[5] - m.z0]
        return max(hits, key=lambda p: p[6] + p[7]) if hits else None


def load_island(path, area):
    return IslandData(px.StageMap(path, area))
