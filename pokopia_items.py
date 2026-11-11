"""Item metadata for browsing: categories, placeable size, icon availability, duplicate names.

The game's item table has no category field that anyone has decoded, so categories here are derived:
ordered keyword rules on the English name, plus whether the item can be placed on an island
(data/map_parts.bin). They are for browsing only and never touch a save.
"""
import re
import pokopia_save as ps
import pokopia_extras as px

# (key, label, colour, glyph). The colour is used for placeholders and map footprints.
CATEGORIES = [
    ('food', 'Food & Drink', '#f08a4b', '🍲'),
    ('crops', 'Crops & Berries', '#e85d75', '🍓'),
    ('seeds', 'Seeds & Plants', '#5cb85c', '🌱'),
    ('materials', 'Materials', '#b08968', '🪵'),
    ('building', 'Building & Terrain', '#8d99ae', '🧱'),
    ('furniture', 'Furniture & Decor', '#c77dff', '🪑'),
    ('lighting', 'Lighting', '#f6c343', '💡'),
    ('nature', 'Outdoor & Nature', '#43aa8b', '🌳'),
    ('kits', 'Kits & Buildings', '#4d96ff', '🏠'),
    ('recipes', 'Recipes', '#ff9f1c', '📜'),
    ('paint', 'Paint & Prints', '#ff6fb5', '🎨'),
    ('gifts', 'Pokémon Gifts', '#ff7b9c', '🎁'),
    ('collect', 'Collectibles & Reading', '#7b8cde', '⭐'),
    ('held', 'Held Items & Badges', '#2ec4b6', '💎'),
    ('other', 'Misc', '#9aa5b1', '❔'),
]
CAT_INDEX = {k: n for n, (k, *_) in enumerate(CATEGORIES)}
CAT_LABEL = {k: label for k, label, *_ in CATEGORIES}
CAT_COLOR = {k: c for k, _, c, _ in CATEGORIES}
CAT_GLYPH = {k: g for k, _, _, g in CATEGORIES}


def _rx(pattern):
    return re.compile(pattern, re.I)


# Ordered (key, regex, also applies to placeable items). The first matching rule wins.
_RULES = [
    ('gifts', _rx(r"['’]s gift$"), True),
    ('recipes', _rx(r'\brecipe'), True),
    ('collect', _rx(r'^♪|trophy|fossil|\brelic\b|^photo #|habitat hint'), True),
    ('collect', _rx(r'#\d|journal|confession|diary|\bnotes?\b|magazine|monthly|weekly|issue\)|report|catalog|'
                    r'message|^how to|guide|manual|\bbook\b|letter|newspaper|diploma|certificate|tablet|slate|'
                    r'treasure map|update$|sale!$|wanted$|^\?\?\?$|memo\b|!$'), False),
    ('held', re.compile(r'^(?=[A-Z])(?i:.*(badge|nugget|never-melt|throat spray|stardust|feather|shard|scale|glasses|'
                        r'sludge|charcoal|ability |band$|herb$|incense|orb$|plate$|claw|fang|leftovers|lens|specs|'
                        r'scarf|belt|powder$|pok.metal|rock$|everstone|stone$|mystic water|tail$|armor$|'
                        r'weather charm|dowsing machine|candy$|shell bell|bell$|policy$|vest$|helmet$|boots$|'
                        r'seed$|berry juice|capsule|ticket|pass$|key$|coin|crown|ball$|ribbon))'), False),
    ('held', _rx(r'(badge|weather charm|dowsing machine)$'), True),
    ('paint', _rx(r'\bpaint\b|paint balloon|\bprint$'), True),
    ('kits', _rx(r'\bkit$|\b(house|cottage|hut|tent|pok.mon center|tower|lab|mansion|castle|station|'
                 r'temple|plaza|shop|chambers|gym|lighthouse|windmill|waterwheel|power plant)$'), True),
    ('crops', _rx(r'berry$|berries$|^(tomato|potato|carrot|fresh carrot|wheat|bean|corn|pumpkin|onion|'
                  r'cabbage|lettuce|cave mushrooms|glowing mushrooms|mushrooms?|seaweed|honey|apple|egg|'
                  r'syrupy apple|watermelon|leek)$|\b(tomato|potato|carrot|wheat|bean|watermelon) plant'), True),
    ('seeds', _rx(r'\bseeds?$|sapling|seedling|sprout|\bbulb$|carrot stem'), True),
    ('food', _rx(r'salad|soup|bread|steak|stew|curry|cake|\bpie$|cookie|sandwich|coffee|\btea$|juice|'
                 r'\bwater$|milk|omelet|pancake|pizza|pasta|\brice\b|sushi|platter|smoothie|latte|cocoa|\bjam$|'
                 r'candy|dessert|pudding|burger|fries|noodles|skewer|toast|\bdish$|snack|malasada|poffin|'
                 r'puff|treat|soda|float$|lemonade|parfait|gratin|croquette|dumpling|tart$|muffin|donut|'
                 r'cr[eê]pe|sweets|bowl$|stir-fry|risotto|onigiri|porridge|cereal|sorbet|ice cream'), False),
    ('lighting', _rx(r'\b(lamp|light|lights|lantern|candle|candles|torch|chandelier|bonfire|streetlight|'
                     r'spotlight)( \(.*\))?$|^neon'), True),
    ('materials', _rx(r'\b(ore|ingot|twine|lumber|stick|clay|concrete|glass|plank|planks|vine rope|rope|'
                      r'leaf|leaves|nails?|screws?|cloth|fabric|wool|cotton|gravel|coal|crystal|resin|rubber|'
                      r'paper|strings?|thread|fluff|fiber|hide|seashell|pebbles?|chunk|supplies|scrap|wire|'
                      r'sap|amber|stone|sand|log|logs|bricks?|fragments?|deposit|pearl|marble|plating|ash|cube|seawater)$'), True),
    ('nature', _rx(r'\btree\b|hedge|grass|flowers?$|bush|shrub|vines?$|cactus|rock$|rocks$|boulder|moss$|'
                   r'mushroom|coral|algae|reeds?$|lily|fern|bamboo|palm|stump|pond|puddle|waterfall|plant$|'
                   r'plants$|kelp|clover|weeds?$|tulips?$|roses?$|sunflowers?$|daisy|lotus|ivy|shoots$|'
                   r'driftwood|cliff|seabed|crops?$|sprouts?$'), True),
    ('building', _rx(r'wall( \(.*\))?$|wall\b.*\((upper|lower|middle|corner|edge)|floor|tiling|tiles?$|'
                     r'\broad\b|\bpath\b|paving|soil|pillar|\bbeam|roof|fence|fencing|steps|stairs|slope|'
                     r'border|\bblocks?\b|bridge|scaffold|railing|\brail|track|\bdoor\b|window|gate|arch\b|'
                     r'column|foundation|platform|ladder|terrain|ground|turf|asphalt|cobble|plaster|panel|'
                     r'partition|siding|awning|walkway|\bsand$|\bsnow\b|\bice\b|lava|magma|\bmud\b|dirt|'
                     r'wallpaper|carpet$|carpeting$|stepping stones|grate|levee'), True),
    ('furniture', _rx(r'poster|guitar|\bbed$|chair|table|sofa|couch|desk|shelf|shelves|\bmat$|\brug$|bag$|'
                      r'\bcan$|television|\btv\b|doll|plush|clock|\bsign\b|statue|fountain|bunting|popper|'
                      r'ship$|figure|toy|generator|perch|cushion|stool|bench|cabinet|dresser|wardrobe|'
                      r'counter|bathtub|toilet|sink|stove|oven|fridge|vase|pot$|basket|box$|chest$|crate|'
                      r'barrel|machine|monitor|computer|speaker|piano|drum|mirror|curtain|flag|banner|'
                      r'painting|picture|frame|ornament|decoration|trash|garbage|bin$|bottle|cup$|mug$|'
                      r'plate$|stand$|rack$|easel|canvas|tent|umbrella|swing|slide$|hammock|bucket'), True),
]


class _Meta:
    def __init__(self):
        self.icons = px.Icons()
        self.placeable = dict(px.placeable_items())
        names = ps.ITEM_NAMES
        wardrobe = set(ps.WARDROBE_IDS)
        self.ids = [i for i in range(1, len(names)) if names[i].strip() and i not in wardrobe]
        # an item counts as placeable if any item with the same name is (variants share one map part)
        by_name = {}
        for i, size in self.placeable.items():
            if 0 < i < len(names):
                by_name.setdefault(names[i], size)
        for i in self.ids:
            if i not in self.placeable and names[i] in by_name:
                self.placeable[i] = by_name[names[i]]
        self.cat = {}
        self.first = {}      # name -> first id with that name
        self.count = {}      # name -> how many ids share it
        for i in self.ids:
            n = names[i]
            self.cat[i] = self._classify(i, n)
            self.first.setdefault(n, i)
            self.count[n] = self.count.get(n, 0) + 1

    def _classify(self, i, name):
        n = name.strip()
        placed = i in self.placeable
        for key, rx, any_item in _RULES:
            if (any_item or not placed) and rx.search(n):
                return key
        if placed:
            return 'furniture'
        if n[:1].isupper():
            return 'collect'   # unplaceable Title Case names are books, headlines and key items
        return 'other'


_META = None


def meta():
    global _META
    if _META is None:
        _META = _Meta()
    return _META


def category(item_id):
    return meta().cat.get(item_id, 'other')


def browsable_ids():
    """Every named item except the unnamed outfit/hairstyle entries."""
    return meta().ids


def placeable(item_id):
    """(width, height, depth) in blocks if the item can be placed on an island, else None."""
    return meta().placeable.get(item_id)


def has_icon(item_id):
    return meta().icons.has_item_icon(item_id)


def duplicate_count(item_id):
    return meta().count.get(ps.ITEM_NAMES[item_id], 1) if 0 < item_id < len(ps.ITEM_NAMES) else 1


def is_first_of_name(item_id):
    return meta().first.get(ps.ITEM_NAMES[item_id]) == item_id


def category_counts():
    c = {}
    for i in meta().ids:
        k = meta().cat[i]
        c[k] = c.get(k, 0) + 1
    return c
