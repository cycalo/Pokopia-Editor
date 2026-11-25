"""Pokopia save format core (CMNDAT.BIN, version 0x0200017D / game 2.0.x).

Format notes (verified against a real save):
  * Every .BIN except S00/SYDAT.BIN is: header + zlib stream.
    - 0x00 u32 magic 0x31227687
    - 0x04 u32 version (CMNDAT 2.0.x = 0x0200017D)
    - 0x08 u32 0x00040001
    - 0x10 u32 active length = header size + compressed size
      (bytes after that are leftover padding and are ignored by the game)
    - CMNDAT header size is 0x130. No extra checksum: integrity is the zlib
      Adler-32, which zlib recomputes on every write.
  * Decompressed CMNDAT is exactly 0x470CED bytes.

Fields marked "own finding" below were located by comparing
G00 with B00 in a real save and are only ever READ, except where noted "advanced".
"""
import os, shutil, struct, sys, zlib, hashlib, datetime, json

MAGIC = 0x31227687
VERSION = 0x0200017D
HEADER_SIZE = 0x130
DATA_SIZE = 0x470CED
NAME_OFS, NAME_SIZE, NAME_COUNT = 0x46E0E5, 25, 9
INV_OFS, INV_COUNT, INV_MAIN, ITEM_SIZE = 0x46ECEA, 130, 120, 5
ITEM_MASK = 0x1FFF
VIL_COUNT, VIL_SIZE = 1050, 374
HOME_OFS, HOME_SIZE = 0x79824, 21
ABIL_OFS = 0x405047
FLAGS_OFS = 0x220F04
FLAG_COUNT = 250
FRIENDSHIP_MAX = 170
PUBLIC_SKILLS = [1, 2, 3, 4, 5, 6, 10, 11, 12, 13]
WHEEL_SKILLS = [1, 2, 3, 4, 5, 6, 12, 13]

SKILL_COUNT, SKILL_SIZE = 64, 8
SKILL_WHEEL_OFS, SKILL_WHEEL_COUNT = ABIL_OFS + SKILL_COUNT * SKILL_SIZE, 8
REACT_OFS, REACT_COUNT = SKILL_WHEEL_OFS + SKILL_WHEEL_COUNT, 128
REACT_WHEEL_OFS, REACT_WHEEL_COUNT = REACT_OFS + REACT_COUNT, 24
REACT_PUBLIC_MAX = 100

# own findings (read only)
PLAYTIME_OFS = 0x223269          # f64 seconds played
VIL_MET_PLAYTIME = 0x1B          # f32 play-time seconds when the resident joined
VIL_MET_DATE = 0x16A             # 6 x u16: year, month, day, hour, minute, second

# Own finding, confirmed in game 2026-11-11: one byte per item ID ("obtained" catalog). Normal items
# use 0x43; outfits and hairstyles are item IDs with no name in the item list and the game marks
# them owned with 1. Setting every one of these to 1 unlocked all 27 outfits plus extra hairstyles.
CATALOG_OFS = 0x402ED9
WARDROBE_IDS = list(range(2389, 2434)) + list(range(2439, 2446)) + list(range(2452, 2501))
WARDROBE_OWNED = 1
# IDs follow the order the game's mirror lists them (own finding, 2026-11-11).
# Outfits: 2397 + position, confirmed in game at 2400, 2403, 2404, 2407, 2411, 2421.
OUTFITS = [(2397 + n, name) for n, name in enumerate([
    'Familiar 1', 'Familiar 2', 'Pokémon Center', 'Team Rocket', 'Rock-solid', 'Ranger', 'Ninja',
    'Psychic Master', 'Black Belt', 'Sailor', 'Super Nerd', 'Roughneck', 'Bird Keeper', 'Red', 'Fresh',
    'Cool', 'Rascal', 'Cozy', 'Sporty', 'Chic', 'Professor', 'Sightseer', 'Mermaid', 'Preschooler',
    'Rad', 'Cheerful', 'Triathlete'], 1)]   # last five are Expansion Pass (Bubbly Basin) outfits; Rad/Cheerful/Triathlete IDs come from the ROM item table
# Hairstyles: mirror order, Shaved is a default with no ID found. Confirmed in game at 2461 Parted,
# 2463 Mermaid, 2472 Side tails; 2459 showed nothing new (Locs is a default). The rest follow the order.
HAIRSTYLES = list(zip(range(2454, 2461), ['Short', 'Pigtails', 'Buns', 'Two-block cut', 'Braided pigtails',
                                          'Locs', 'Curly'])) + [(None, 'Shaved')] + \
    list(zip(range(2461, 2473), ['Parted', 'Fluffy', 'Mermaid', 'Winged pigtails', 'Sideswept', 'Simple',
                                 'Long bangs', 'Long', 'Crested', 'Ponytail', 'Messy short', 'Side tails']))
# available without being stored as owned (Familiar 1/2 and the starting hairstyles)
WARDROBE_DEFAULTS = {2398, 2399, 2454, 2455, 2456, 2457, 2458, 2459, None}
WARDROBE_CONFIRMED = {2400, 2403, 2404, 2407, 2411, 2414, 2421, 2460, 2461, 2463, 2466, 2472}
KNOWN_WARDROBE = {i: f'{n} outfit' for i, n in OUTFITS}
KNOWN_WARDROBE.update({i: f'{n} hairstyle' for i, n in HAIRSTYLES if i})


def wardrobe_lookup(text):
    """Item ID for an outfit/hairstyle name or number, e.g. 'Ranger', 'outfit:Mermaid', 'hair:mermaid', '2403'."""
    t = text.strip().lower()
    if t.isdigit():
        i = int(t)
        if i not in WARDROBE_IDS:
            raise ValueError(f'{i} is not a wardrobe entry')
        return i
    kind, _, name = t.rpartition(':')
    pools = {'outfit': OUTFITS, 'hair': HAIRSTYLES, 'hairstyle': HAIRSTYLES}
    pool = pools.get(kind, OUTFITS + HAIRSTYLES)
    hits = [i for i, n in pool if n.lower() == name]
    if len(hits) > 1:
        raise ValueError(f'"{text}" is both an outfit and a hairstyle; write outfit:{name} or hair:{name}')
    if not hits or hits[0] is None:
        raise ValueError(f'No unlockable outfit or hairstyle called "{text}"')
    return hits[0]

# Function flags: id -> (label, group, source). Sources:
#   'game'    behaviour checked in game
#   'data'    certain from the game's own code and data (docs/function-flags-research.md), not tested in game
#   'guess'   best reading of the game's code and data, unconfirmed
FLAG_SOURCES = {
    'game': ('Tested in game', 'Behaviour has been checked in the game.'),
    'data': ('From game data', "Read from the game's own code and data; not tested in game."),
    'guess': ('Best guess', "Most likely meaning from the game's code and data; unconfirmed."),
}
FLAG_GROUPS = ['Moves & travel', 'Specialties', 'Food & cooking', 'Bag & upgrades', 'Poké Center & PC',
               'Crafting & painting', 'Pokémon comfort info', 'Areas & story', 'Game & menus']
FLAG_INFO = {
    54: ('Liquid absorption (Water Gun)', 'Moves & travel', 'game'),
    56: ('Surf permission', 'Moves & travel', 'game'),
    57: ('Glide permission', 'Moves & travel', 'game'),
    148: ('Dive (Surf)', 'Moves & travel', 'game'),
    82: ('Jump unlocked', 'Moves & travel', 'guess'),
    15: ('Rock Smash learned', 'Moves & travel', 'guess'),
    20: ('Stockpile / Spit Out', 'Moves & travel', 'guess'),
    53: ('Stockpile / Spit Out', 'Moves & travel', 'guess'),
    79: ('Paint specialty unlocked (Painting)', 'Specialties', 'data'),
    84: ('Gather Honey specialty unlocked', 'Specialties', 'data'),
    99: ('Illuminate specialty unlocked', 'Specialties', 'data'),
    109: ('Yawn specialty unlocked', 'Specialties', 'data'),
    116: ('Engineer specialty unlocked', 'Specialties', 'data'),
    118: ('DJ specialty unlocked', 'Specialties', 'data'),
    32: ('Storage specialty', 'Specialties', 'guess'),
    33: ('Storage specialty', 'Specialties', 'guess'),
    47: ('Grow specialty', 'Specialties', 'guess'),
    71: ('Leafage food boost', 'Food & cooking', 'game'),
    72: ('Cut food boost', 'Food & cooking', 'game'),
    73: ('Water Gun food boost', 'Food & cooking', 'game'),
    74: ('Rock Smash food boost', 'Food & cooking', 'game'),
    125: ('Rock Smash extra food effect', 'Food & cooking', 'game'),
    153: ('Surf food boost', 'Food & cooking', 'game'),
    67: ('Cooking: cutting board', 'Food & cooking', 'guess'),
    69: ('Cooking: cutting board', 'Food & cooking', 'guess'),
    68: ('Cooking: bread oven', 'Food & cooking', 'guess'),
    70: ('Cooking: frying pan', 'Food & cooking', 'guess'),
    63: ('Bag upgrade 1 (30 slots)', 'Bag & upgrades', 'data'),
    64: ('Bag upgrade 2 (60 slots)', 'Bag & upgrades', 'data'),
    65: ('Bag upgrade 3 (90 slots)', 'Bag & upgrades', 'data'),
    66: ('Bag upgrade 4 (120 slots)', 'Bag & upgrades', 'data'),
    102: ('PP upgrade 1', 'Bag & upgrades', 'data'),
    103: ('PP upgrade 2', 'Bag & upgrades', 'data'),
    104: ('PP upgrade 3', 'Bag & upgrades', 'data'),
    105: ('PP upgrade 4', 'Bag & upgrades', 'data'),
    107: ('Handy bag bought (secondary bar)', 'Bag & upgrades', 'data'),
    129: ('Tripod bought', 'Bag & upgrades', 'data'),
    7: ('Poké Center PC unlocked', 'Poké Center & PC', 'guess'),
    27: ('PC challenges unlocked', 'Poké Center & PC', 'guess'),
    28: ('PC Link Play unlocked', 'Poké Center & PC', 'guess'),
    30: ('PC shop unlocked', 'Poké Center & PC', 'guess'),
    108: ('PC stamps unlocked', 'Poké Center & PC', 'guess'),
    114: ('PC appraisal unlocked', 'Poké Center & PC', 'guess'),
    133: ('PC environment level unlocked', 'Poké Center & PC', 'guess'),
    4: ('Pokémon Center healing', 'Poké Center & PC', 'guess'),
    3: ('Workbench unlocked', 'Crafting & painting', 'guess'),
    135: ('Workbench Craft option', 'Crafting & painting', 'guess'),
    77: ('Patterns unlocked (needs Painting)', 'Crafting & painting', 'guess'),
    78: ('Multiple paint areas unlocked (needs Painting)', 'Crafting & painting', 'guess'),
    22: ('Environment level shown', 'Pokémon comfort info', 'guess'),
    23: ('Home brightness shown', 'Pokémon comfort info', 'guess'),
    24: ('Home temperature shown', 'Pokémon comfort info', 'guess'),
    25: ('Home humidity shown', 'Pokémon comfort info', 'guess'),
    26: ('Things Pokémon like shown', 'Pokémon comfort info', 'guess'),
    37: ('Food comfort shown', 'Pokémon comfort info', 'guess'),
    38: ('Things Pokémon dislike shown', 'Pokémon comfort info', 'guess'),
    11: ('Pokémon traces / habitat clues', 'Pokémon comfort info', 'guess'),
    86: ('Withered Wasteland milestone', 'Areas & story', 'data'),
    87: ('Bleak Beach milestone', 'Areas & story', 'data'),
    88: ('Rocky Ridges milestone', 'Areas & story', 'data'),
    89: ('Sparkling Skylands milestone', 'Areas & story', 'data'),
    151: ('Bubbly Basin milestone', 'Areas & story', 'data'),
    149: ('Bubbly Basin access', 'Areas & story', 'guess'),
    150: ('Bubbly Basin access', 'Areas & story', 'guess'),
    18: ('Wake at home on load', 'Game & menus', 'guess'),
    76: ('Pause menu unlocked', 'Game & menus', 'guess'),
    19: ('Game treats it as on whatever the save says', 'Game & menus', 'data'),
    142: ('Never set by the game (cut feature?)', 'Game & menus', 'data'),
}
# flags 160-249 are never read or set anywhere in the game (docs/function-flags-research.md)
FLAG_UNUSED_FROM = 160
# plain labels for the CLI, the save report and the legacy GUI
KNOWN_FLAGS = {i: lab + (' (unconfirmed)' if src == 'guess' else '') for i, (lab, _, src) in FLAG_INFO.items()}
# key -> (label, flags it sets, key that must be on first).
UPGRADES = {
    'bag1': ('Bag upgrade 1', (63,), None),
    'bag2': ('Bag upgrade 2', (64,), 'bag1'),
    'bag3': ('Bag upgrade 3', (65,), 'bag2'),
    'bag4': ('Bag upgrade 4', (66,), 'bag3'),
    'pp1': ('PP upgrade 1', (102,), None),
    'pp2': ('PP upgrade 2', (103,), 'pp1'),
    'pp3': ('PP upgrade 3', (104,), 'pp2'),
    'pp4': ('PP upgrade 4', (105,), 'pp3'),
    'jump': ('Jump', (82,), None),
    'paint': ('Painting', (79,), None),
    'patterns': ('Paint patterns', (77,), 'paint'),
    'paintareas': ('Multiple paint areas', (78,), 'paint'),
    'workbench': ('Workbench + Craft option', (3, 135), None),
    'pc': ('Poké Center PC', (7,), None),
    'pcshop': ('PC shop', (30,), 'pc'),
    'pcchallenges': ('PC challenges', (27,), 'pc'),
    'pcstamps': ('PC stamps', (108,), 'pc'),
    'pcappraisal': ('PC appraisal', (114,), 'pc'),
    'pcenv': ('PC environment level', (133,), 'pc'),
    'pclink': ('PC Link Play', (28,), 'pc'),
}
# key -> (label, flags to set, required learned move, required other extra)
EXTRAS = {
    'absorb': ('Liquid Absorption', (54,), 3, None),
    'dive': ('Dive', (148,), 10, None),
    'boost1': ('Leafage food boost', (71,), 1, None),
    'boost5': ('Cut food boost', (72,), 5, None),
    'boost3': ('Water Gun food boost', (73,), 3, None),
    'boost4': ('Rock Smash food boost', (74, 125), 4, None),
    'boost10': ('Surf food boost', (153,), 10, 'dive'),
}

HERE = getattr(sys, '_MEIPASS', None) or os.path.dirname(os.path.abspath(__file__))  # bundle dir in the exe


def _names(kind):
    p = os.path.join(HERE, 'data', kind + '.txt')
    try:
        with open(p, encoding='utf-8') as f:
            return f.read().replace('\r', '').split('\n')
    except OSError:
        return []


ITEM_NAMES = _names('item')
VILLAGER_NAMES = _names('villager')
SKILL_NAMES = _names('skill')
AREA_NAMES = _names('area')
REACTION_NAMES = _names('reaction')
DEX_NAMES = _names('dex')
HABITAT_NAMES = _names('habitat')
FRAME_NAMES = _names('photoframe')
FILTER_NAMES = _names('photofilter')
PHOTOOP_NAMES = _names('photoop')
PUBLIC_REACTIONS = [i for i in range(1, min(REACT_PUBLIC_MAX + 1, len(REACTION_NAMES))) if REACTION_NAMES[i].strip()]


# Content tags. Items: data/item_tag.bin, built from the game's own item table by tools/extract_item_tags.py.
# Outfits and hairstyles: the published Expansion Pass lists. Residents: the game keeps event Pokémon in the 505-527
# ID block and Bubbly Basin Pokémon in 554-607 (inferred from the blocks, not a per-Pokémon flag).
TAG_DLC, TAG_EVENT = 1, 2
TAG_LABEL = {TAG_DLC: 'DLC', TAG_EVENT: 'Event'}
TAG_LONG = {TAG_DLC: 'Expansion Pass (Bubbly Basin)', TAG_EVENT: 'Limited-time event'}
TAG_COLOR = {TAG_DLC: '#3b9ddd', TAG_EVENT: '#e08a2e'}
try:
    with open(os.path.join(HERE, 'data', 'item_tag.bin'), 'rb') as _f:
        ITEM_TAGS = _f.read()
except OSError:
    ITEM_TAGS = b''
WARDROBE_DLC = {2420, 2421, 2422, 2423, 2424,     # Mermaid, Preschooler, Rad, Cheerful, Triathlete outfits
                2468, 2469, 2470, 2471, 2472}     # Long, Crested, Ponytail, Messy short, Side tails hairstyles


def _u16_table(name):
    try:
        with open(os.path.join(HERE, 'data', name), 'rb') as f:
            b = f.read()
        return struct.unpack(f'<{len(b) // 2}H', b)
    except OSError:
        return ()


# Collection records (Pokédex, habitat dex, crafting recipes, cooking, photo frames/filters). The save offsets were
# first published by PokoHex (SaveLayout / Catalogue) and checked against a real 2.0.x save: every non-public index
# is zero and the states match the in-game progress. Pokédex, habitats and crafting recipes confirmed in game
# 2026-11-15. The index tables in data/ are built from the game files by tools/extract_catalog_tables.py.
DEX_OFS, DEX_COUNT = 0x426EFF, 1024               # 1 byte per dex slot: bit 3 seen, bits 0+1 registered
HABITAT_OFS, HABITAT_COUNT, HABITAT_SIZE = 0x4256FF, 512, 12   # byte 0: bit 0 discovered, bit 1 built
RECIPE_OFS, RECIPE_COUNT, RECIPE_SIZE = 0x3FCB4C, 1500, 6      # u16 +2 learned order, byte +4 bit 1 learned
COOK_OFS, COOK_COUNT = 0x3FEE74, 101              # 1 byte per cooking-table row, bit 0 known
PHOTO_STYLE_OFS, FRAME_COUNT, FILTER_COUNT = 0x467E5E + 128, 64, 16   # 1 byte each, bit 0 unlocked; index 0 = none
COINS_OFS, COINS_MAX = 0x46D080, 999999           # i32 Life Coins
# Own findings (2026-11-15, from a save the user made right after finding two artifacts in game): Human Records and
# Ancient Artifacts are two byte arrays side by side, 300 entries each. Records are indexed by record number (the item
# table's sub-index of a record item), artifacts by the row of the game's artifact table. 1 = found; the game adds
# bit 1 (value 3) while the entry still carries its 'new' mark.
# The state/date arrays at 0x2208DF / 0x21A0B6 are something else (not records): never write them.
RECORD_OFS, RECORD_COUNT = 0x4670BC, 182
ARTIFACT_OFS, ARTIFACT_ROWS = 0x4671E8, 300
PHOTOOP_OFS, PHOTOOP_COUNT = 0x467E5E, 128        # Highlight Reel: 1 byte per photo op, bit 0 completed
CATALOG_OBTAINED = 0x43                           # catalog byte the game writes for a normal item
RECORD_ITEM = _u16_table('catalog_records.bin')   # record number -> item ID with its name (0 = no item)
_ART = _u16_table('catalog_artifacts.bin')        # pairs: item ID, section | group << 8
ARTIFACT_SECTION = {1: 'Lost Relics (L)', 2: 'Lost Relics (S)', 3: 'Fossils', 8: 'Treasure Maps'}
ARTIFACTS = {}                                    # artifact table row -> (item ID, section)
for _k in range(0, min(len(_ART), ARTIFACT_ROWS * 2) - 1, 2):
    if _ART[_k]:
        ARTIFACTS[_k // 2] = (_ART[_k], _ART[_k + 1] & 0xFF)
try:
    with open(os.path.join(HERE, 'data', 'item_group.bin'), 'rb') as _f:
        ITEM_GROUP = _f.read()     # per item ID: 0 not in the item list, 1 main, 2 event, 3 Bubbly Basin, 6 building parts
except OSError:
    ITEM_GROUP = b''
_DEX_ROWS = _u16_table('catalog_dex.bin')
DEX_RESIDENT = _u16_table('catalog_residents.bin')     # dex slot -> resident index (for the name and portrait)
RECIPE_ITEM = _u16_table('catalog_recipes.bin')        # recipe index -> item ID it crafts
COOK_ITEM = _u16_table('catalog_cooking.bin')          # cooking row -> dish item ID (a dish can have several rows)


def _named(lst, i):
    return 0 <= i < len(lst) and bool(lst[i].strip())


def _dex_name(i):
    r = DEX_RESIDENT[i] if i < len(DEX_RESIDENT) else 0
    return VILLAGER_NAMES[r] if r and _named(VILLAGER_NAMES, r) else DEX_NAMES[i]


COOK_ROWS = {}
for _row, _item in enumerate(COOK_ITEM[:COOK_COUNT]):
    if _row and _item and _named(ITEM_NAMES, _item):
        COOK_ROWS.setdefault(_item, []).append(_row)
# kind -> [(id, name)]. IDs: dex slot, habitat number, recipe index, dish item ID, frame number, filter number.
COLLECTION = {
    'dex': [(i, _dex_name(i)) for i in range(1, min(DEX_COUNT, len(_DEX_ROWS), len(DEX_NAMES)))
            if _DEX_ROWS[i] != 0xFFFF and _named(DEX_NAMES, i)],
    'habitat': [(i, HABITAT_NAMES[i]) for i in range(1, min(HABITAT_COUNT, len(HABITAT_NAMES))) if _named(HABITAT_NAMES, i)],
    'recipe': [(i, ITEM_NAMES[RECIPE_ITEM[i]]) for i in range(1, min(RECIPE_COUNT, len(RECIPE_ITEM)))
               if RECIPE_ITEM[i] and _named(ITEM_NAMES, RECIPE_ITEM[i])],
    'cooking': [(i, ITEM_NAMES[i]) for i in sorted(COOK_ROWS)],
    'frame': [(i, FRAME_NAMES[i]) for i in range(1, min(FRAME_COUNT, len(FRAME_NAMES))) if _named(FRAME_NAMES, i)],
    'filter': [(i, FILTER_NAMES[i]) for i in range(1, min(FILTER_COUNT, len(FILTER_NAMES))) if _named(FILTER_NAMES, i)],
    'item': [(i, ITEM_NAMES[i]) for i in range(1, min(len(ITEM_GROUP), len(ITEM_NAMES)))
             if ITEM_GROUP[i] and _named(ITEM_NAMES, i)],
    'record': [(n, ITEM_NAMES[RECORD_ITEM[n]]) for n in range(1, min(RECORD_COUNT, len(RECORD_ITEM)))
               if RECORD_ITEM[n] and _named(ITEM_NAMES, RECORD_ITEM[n])],
    'artifact': [(row, f'{ITEM_NAMES[i] if _named(ITEM_NAMES, i) else f"Item {i}"}  ({ARTIFACT_SECTION.get(s, "other")})')
                 for row, (i, s) in ARTIFACTS.items()],
    'photoop': [(i, PHOTOOP_NAMES[i]) for i in range(1, min(PHOTOOP_COUNT, len(PHOTOOP_NAMES))) if _named(PHOTOOP_NAMES, i)],
}
_COLLECTION_IDS = {k: {i for i, _ in v} for k, v in COLLECTION.items()}
# kind -> (title, name of state 1 or '', name of state 2)
COLLECTION_INFO = {
    'dex': ('Pokédex', 'seen', 'registered'),
    'habitat': ('Habitat Dex', 'discovered', 'built'),
    'recipe': ('Crafting recipes', '', 'learned'),
    'cooking': ('Cooking recipes', 'partly known', 'known'),
    'frame': ('Photo frames', '', 'unlocked'),
    'filter': ('Photo filters', '', 'unlocked'),
    'item': ('Item list', '', 'obtained'),
    'record': ('Human Records', '', 'found'),
    'artifact': ('Ancient Artifacts', '', 'found'),
    'photoop': ('Highlight Reel', '', 'completed'),
}


# Quests. Own finding, checked against the game's quest tables 2026-11-25 (not edited in game yet): one u16 state per
# quest id at QUEST_OFS + 2 * id. The game's states: 1 not started, 2 seen only briefly in older saves (taken here as
# "unlocked"), 3 in progress, 4 done. A user, MrGrangerplays, first reported the offset and names for the Wasteland.
# data/quests.json (tools/extract_quest_table.py) holds what each quest does when it starts and when it is done.
QUEST_OFS, QUEST_COUNT = 0x221F5C, 1001
QUEST_NOT_STARTED, QUEST_UNLOCKED, QUEST_ACTIVE, QUEST_DONE = 1, 2, 3, 4
QUEST_STATES = {QUEST_NOT_STARTED: 'Not started', QUEST_UNLOCKED: 'Unlocked', QUEST_ACTIVE: 'In progress',
                QUEST_DONE: 'Done'}
QUEST_AREAS = [(1, 160, AREA_NAMES[1] if len(AREA_NAMES) > 1 else 'Area 1'),
               (161, 320, AREA_NAMES[2] if len(AREA_NAMES) > 2 else 'Area 2'),
               (321, 480, AREA_NAMES[3] if len(AREA_NAMES) > 3 else 'Area 3'),
               (481, 640, AREA_NAMES[4] if len(AREA_NAMES) > 4 else 'Area 4'),
               (641, 800, 'Other quests'),
               (801, 1000, AREA_NAMES[5] if len(AREA_NAMES) > 5 else 'Area 5')]
# command types the editor can carry out itself; every other type changes the world or runs a game event
QCMD_FLAGS, QCMD_MOVE, QCMD_RECIPE, QCMD_FLAG = 1, 2, 3, 0x19


def _json(name):
    try:
        with open(os.path.join(HERE, 'data', name), encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


QUESTS = {int(k): v for k, v in _json('quests.json').items()}
QUEST_NAMES = {int(k): v for k, v in _json('quest_names.json').get('names', {}).items()}


def quest_area(q):
    for lo, hi, name in QUEST_AREAS:
        if lo <= q <= hi:
            return name
    return ''


def quest_effects(q, phase='done'):
    """What quest q does when it starts or is done, as (kind, value) pairs: ('flag', id), ('unflag', id),
    ('move', skill id), ('recipe', recipe row) or ('other', command type)."""
    out = []
    for cmd in QUESTS.get(q, {}).get(phase, []):
        t, p = cmd[0], cmd[1:] + [0] * 8
        if t == QCMD_FLAGS:
            out += [('flag', f) for f in p[:4] if f]
        elif t == QCMD_FLAG:
            out.append(('flag' if p[1] else 'unflag', p[0]))
        elif t == QCMD_MOVE:
            out.append(('move', p[0]))
        elif t == QCMD_RECIPE:
            out.append(('recipe', p[0]))
        else:
            out.append(('other', t))
    return out


def describe_effect(kind, v):
    if kind in ('flag', 'unflag'):
        return f'flag {v}{" off" if kind == "unflag" else ""}' + (f' ({KNOWN_FLAGS[v]})' if v in KNOWN_FLAGS else '')
    if kind == 'move':
        return 'teaches ' + name_of(SKILL_NAMES, v, 'move')
    if kind == 'recipe':
        item = RECIPE_ITEM[v] if v < len(RECIPE_ITEM) else 0
        return 'recipe ' + (ITEM_NAMES[item] if _named(ITEM_NAMES, item) else str(v))
    return ''


def quest_summary(q):
    """Short line on what finishing quest q gives, from the game's quest table (for list rows)."""
    eff = quest_effects(q)
    parts = [('teaches ' if k == 'move' else '') + describe_effect(k, v).replace('teaches ', '').replace('recipe ', '')
             + (' recipe' if k == 'recipe' else '') for k, v in eff if k in ('move', 'recipe')]
    flags = sum(1 for k, _ in eff if k == 'flag')
    if flags:
        parts.append(f'{flags} story flag{"s" if flags > 1 else ""}')
    return ' · '.join(parts)


# Quest kinds (record byte +0xA8). 1 = Pokémon request: its title comes from the game (see the extractor). The main
# story kinds were read from what the quests do (raise the environment level, Yawn up a storm, Team Initiation).
QUEST_REQUEST_KIND = 1
QUEST_MAIN_KINDS = {7, 9, 15, 18}


def quest_type(q):
    k = QUESTS.get(q, {}).get('kind')
    return 'Request' if k == QUEST_REQUEST_KIND else 'Main story' if k in QUEST_MAIN_KINDS else 'Story step'


def quest_name(q):
    """In-game title when the game files give one, else the name a player mapped, else ''."""
    return QUESTS.get(q, {}).get('title') or QUEST_NAMES.get(q, '')


def quest_name_source(q):
    return 'game' if QUESTS.get(q, {}).get('title') else 'player' if q in QUEST_NAMES else ''


def collection_item(kind, i):
    """Item ID behind a recipe or dish (0 for the other kinds)."""
    if kind == 'record':
        return RECORD_ITEM[i] if i < len(RECORD_ITEM) else 0
    if kind == 'artifact':
        return ARTIFACTS[i][0] if i in ARTIFACTS else 0
    return RECIPE_ITEM[i] if kind == 'recipe' else i if kind in ('cooking', 'item') else 0


def item_tag(i):
    """0, TAG_DLC or TAG_EVENT for an item, outfit or hairstyle ID."""
    if i in WARDROBE_DLC:
        return TAG_DLC
    return ITEM_TAGS[i] if i and 0 < i < len(ITEM_TAGS) else 0


def villager_tag(i):
    return TAG_DLC if 554 <= i <= 607 else TAG_EVENT if 505 <= i <= 527 else 0


def name_of(lst, i, prefix):
    if 0 <= i < len(lst) and lst[i].strip():
        return lst[i]
    return f'{prefix} {i}'


def item_name(i):
    return name_of(ITEM_NAMES, i, 'Item') if i else '(empty)'


def fmt_playtime(sec):
    sec = int(sec)
    return f'{sec // 3600}h {sec % 3600 // 60:02}m'


class FormatError(Exception):
    pass


class CommonSave:
    def __init__(self, path):
        self.path = path
        with open(path, 'rb') as f:
            self.original = f.read()
        o = self.original
        if len(o) < HEADER_SIZE:
            raise FormatError('File too small')
        magic, ver, v8 = struct.unpack_from('<III', o, 0)
        if magic != MAGIC:
            raise FormatError(f'Bad magic {magic:#x}')
        if ver != VERSION:
            raise FormatError(f'Unsupported CMNDAT version {ver:#010x} (supported {VERSION:#010x}). Refusing to edit.')
        if v8 != 0x40001:
            raise FormatError(f'Unexpected header field {v8:#x}')
        length = struct.unpack_from('<I', o, 0x10)[0]
        if not (HEADER_SIZE < length <= len(o)):
            raise FormatError('Compressed length field is invalid')
        d = zlib.decompressobj()
        try:
            raw = d.decompress(o[HEADER_SIZE:length])
        except zlib.error as e:
            raise FormatError(f'zlib error: {e}')
        if not d.eof or d.unused_data:
            raise FormatError('zlib stream does not end exactly at the length field')
        if len(raw) != DATA_SIZE:
            raise FormatError(f'Decompressed size {len(raw)} != expected {DATA_SIZE}')
        self.orig_data = raw
        self.data = bytearray(raw)
        self._shadow = bytearray(raw)
        self._undo, self._redo = [], []
        self.player_name  # validate

    @classmethod
    def from_data(cls, raw):
        """A file-less view over decompressed data (for comparisons)."""
        self = cls.__new__(cls)
        self.path = self.original = None
        self.orig_data = bytes(raw)
        self.data = bytearray(raw)
        self._shadow = bytearray(raw)
        self._undo, self._redo = [], []
        return self

    def pending_changes(self):
        """What the edits made so far change, as readable lines."""
        return describe_changes(CommonSave.from_data(self.orig_data), self)

    # ---------- generic ----------
    @property
    def edited(self):
        return bytes(self.data) != self.orig_data

    def to_bytes(self):
        if not self.edited:
            return self.original
        comp = zlib.compress(bytes(self.data), 1)  # level 1 matches the game's own output
        length = HEADER_SIZE + len(comp)
        out = bytearray(max(length, len(self.original)))
        out[:HEADER_SIZE] = self.original[:HEADER_SIZE]
        out[HEADER_SIZE:length] = comp
        struct.pack_into('<I', out, 0x10, length)
        return bytes(out)

    # ---------- undo / redo journal ----------
    def commit(self, label):
        """Record everything changed since the last commit as one undo step. Returns True if anything changed."""
        patches = _diff_patches(self._shadow, self.data)
        if not patches:
            return False
        for ofs, _, new in patches:
            self._shadow[ofs:ofs + len(new)] = new
        self._undo.append((label, patches))
        self._redo.clear()
        return True

    def rollback(self):
        """Drop uncommitted changes (used when an edit fails half way)."""
        for ofs, old, _ in _diff_patches(self._shadow, self.data):
            self.data[ofs:ofs + len(old)] = old

    def undo(self):
        if not self._undo:
            return None
        label, patches = self._undo.pop()
        for ofs, old, _ in patches:
            self.data[ofs:ofs + len(old)] = old
            self._shadow[ofs:ofs + len(old)] = old
        self._redo.append((label, patches))
        return label

    def redo(self):
        if not self._redo:
            return None
        label, patches = self._redo.pop()
        for ofs, _, new in patches:
            self.data[ofs:ofs + len(new)] = new
            self._shadow[ofs:ofs + len(new)] = new
        self._undo.append((label, patches))
        return label

    @property
    def history(self):
        return [label for label, _ in self._undo]

    @property
    def can_redo(self):
        return bool(self._redo)

    # ---------- player ----------
    def _read_name(self, ofs):
        b = bytes(self.data[ofs:ofs + NAME_SIZE])
        if 0 not in b:
            raise FormatError('Player name not terminated')
        return b[:b.index(0)].decode('utf-8')

    @property
    def player_name(self):
        for i in range(NAME_COUNT):
            ofs = NAME_OFS + i * NAME_SIZE
            if self.data[ofs]:
                return self._read_name(ofs)
        return self._read_name(NAME_OFS)

    @player_name.setter
    def player_name(self, value):
        if not value.strip() or any(ord(c) < 32 for c in value):
            raise ValueError('Name must be non-empty with no control characters')
        b = value.encode('utf-8')
        if len(b) >= NAME_SIZE:
            raise ValueError(f'Name must be at most {NAME_SIZE - 1} UTF-8 bytes')
        old = self.player_name
        for i in range(NAME_COUNT):
            ofs = NAME_OFS + i * NAME_SIZE
            if self._read_name(ofs) == old:
                self.data[ofs:ofs + NAME_SIZE] = b.ljust(NAME_SIZE, b'\0')

    @property
    def play_seconds(self):
        """Own finding, read only. Returns None if the value does not look like a play time."""
        v = struct.unpack_from('<d', self.data, PLAYTIME_OFS)[0]
        return v if 0 <= v < 3.6e7 else None

    # ---------- inventory ----------
    def get_slot(self, i):
        ofs = INV_OFS + i * ITEM_SIZE
        rawv = struct.unpack_from('<I', self.data, ofs)[0]
        return rawv & ITEM_MASK, self.data[ofs + 4], rawv

    def set_slot(self, i, item_id, count):
        if not 0 <= i < INV_COUNT:
            raise ValueError('Slot out of range')
        if not 0 <= item_id <= ITEM_MASK:
            raise ValueError('Item ID out of range (0-8191)')
        if not 0 <= count <= 255:
            raise ValueError('Count must be 0-255')
        ofs = INV_OFS + i * ITEM_SIZE
        if item_id == 0 or count == 0:
            self.data[ofs:ofs + 5] = b'\0' * 5
            return
        cur_id, _, rawv = self.get_slot(i)
        if cur_id != item_id:
            rawv = 0  # variant/placement bits belong to the old item
        rawv = (rawv & ~ITEM_MASK) | item_id
        struct.pack_into('<IB', self.data, ofs, rawv, count)

    def filled_slots(self):
        return [i for i in range(INV_COUNT) if self.get_slot(i)[0]]

    def first_empty(self, start=0, end=INV_MAIN):
        for i in range(start, end):
            if self.get_slot(i)[0] == 0:
                return i
        return None

    def add_item(self, item_id, count):
        """Put an item in the first empty main slot. Returns the slot."""
        if item_id == 0 or count == 0:
            raise ValueError('Pick an item and a count above 0')
        i = self.first_empty()
        if i is None:
            raise ValueError('No empty slot in the main bag')
        self.set_slot(i, item_id, count)
        return i

    def set_count(self, i, count):
        item_id = self.get_slot(i)[0]
        if item_id:
            self.set_slot(i, item_id, count)

    def swap_slots(self, i, j):
        for k in (i, j):
            if not 0 <= k < INV_COUNT:
                raise ValueError('Slot out of range')
        a, b = INV_OFS + i * ITEM_SIZE, INV_OFS + j * ITEM_SIZE
        ra, rb = bytes(self.data[a:a + 5]), bytes(self.data[b:b + 5])
        self.data[a:a + 5], self.data[b:b + 5] = rb, ra

    def sort_main(self, by_name=False):
        """Pack the main bag to the front, ordered by item ID or name. The second bar is left alone."""
        recs = []
        for i in range(INV_MAIN):
            ofs = INV_OFS + i * ITEM_SIZE
            if self.get_slot(i)[0]:
                recs.append(bytes(self.data[ofs:ofs + 5]))
        ident = lambda r: struct.unpack_from('<I', r)[0] & ITEM_MASK
        recs.sort(key=(lambda r: (item_name(ident(r)).lower(), ident(r))) if by_name else ident)
        recs += [b'\0' * 5] * (INV_MAIN - len(recs))
        self.data[INV_OFS:INV_OFS + INV_MAIN * ITEM_SIZE] = b''.join(recs)

    def export_bag(self):
        return [dict(slot=i, id=self.get_slot(i)[0], count=self.get_slot(i)[1], name=item_name(self.get_slot(i)[0]))
                for i in self.filled_slots()]

    def import_bag(self, entries, clear=True):
        entries = [(int(e['slot']), int(e['id']), int(e['count'])) for e in entries]
        for slot, item_id, count in entries:  # validate everything before touching data
            if not (0 <= slot < INV_COUNT and 0 < item_id <= ITEM_MASK and 0 < count <= 255):
                raise ValueError(f'Bad preset entry: slot {slot}, item {item_id}, count {count}')
        if clear:
            self.data[INV_OFS:INV_OFS + INV_COUNT * ITEM_SIZE] = bytes(INV_COUNT * ITEM_SIZE)
        for slot, item_id, count in entries:
            self.set_slot(slot, item_id, count)

    # ---------- villagers ----------
    def villager_present(self, i):
        b = self.data[i * VIL_SIZE + 1:i * VIL_SIZE + 17]
        return any(b)

    def villagers(self):
        return [i for i in range(VIL_COUNT) if self.villager_present(i)]

    def get_villager(self, i):
        o = i * VIL_SIZE
        d = self.data
        fr, thank = struct.unpack_from('<HH', d, o + 0x11)
        h = HOME_OFS + i * HOME_SIZE
        htype = d[h]
        stage = d[h + 3]
        y, mo, da, hh, mi, ss = struct.unpack_from('<6H', d, o + VIL_MET_DATE)
        met = None
        if 2020 <= y < 2100 and 1 <= mo <= 12 and 1 <= da <= 31 and hh < 24 and mi < 60 and ss < 60:
            try:
                met = datetime.datetime(y, mo, da, hh, mi, ss)
            except ValueError:
                met = None
        pt = struct.unpack_from('<f', d, o + VIL_MET_PLAYTIME)[0]
        return dict(index=i, name=name_of(VILLAGER_NAMES, i, 'Resident'), friendship=fr, thank_points=thank,
                    present_level=d[o + 0x15], waiting_present=bool(d[o + 0x16]),
                    name_talk_done=bool(d[o + 0xC4]), home_type=htype, home_area=stage,
                    home_area_name=name_of(AREA_NAMES, stage, 'Area') if htype else '',
                    home_uid=struct.unpack_from('<H', d, h + 1)[0],
                    home_xyz=struct.unpack_from('<3h', d, h + 6) if htype else None,
                    met=met, met_playtime=pt if 0 < pt < 3.6e7 else None)

    def _need_villager(self, i):
        if not (0 <= i < VIL_COUNT and self.villager_present(i)):
            raise ValueError('That resident is not in this save')

    def set_friendship(self, i, value):
        self._need_villager(i)
        if not 0 <= value <= 0xFFFF:
            raise ValueError('Friendship must be 0-65535')
        struct.pack_into('<H', self.data, i * VIL_SIZE + 0x11, value)

    def set_name_talk_done(self, i, done):
        self._need_villager(i)
        self.data[i * VIL_SIZE + 0xC4] = 1 if done else 0

    def set_thank_points(self, i, value):
        """Advanced: unverified, normally read only."""
        self._need_villager(i)
        if not 0 <= value <= 0xFFFF:
            raise ValueError('Thank points must be 0-65535')
        struct.pack_into('<H', self.data, i * VIL_SIZE + 0x13, value)

    def set_present_level(self, i, value):
        """Advanced: unverified, normally read only."""
        self._need_villager(i)
        if not 0 <= value <= 255:
            raise ValueError('Present level must be 0-255')
        self.data[i * VIL_SIZE + 0x15] = value

    # ---------- function flags ----------
    def get_flag(self, i):
        if not 1 <= i < FLAG_COUNT:
            raise ValueError(f'Flag must be 1-{FLAG_COUNT - 1}')
        return bool(self.data[FLAGS_OFS + (i >> 3)] >> (i & 7) & 1)

    def set_flag(self, i, on):
        if not 1 <= i < FLAG_COUNT:
            raise ValueError(f'Flag must be 1-{FLAG_COUNT - 1}')
        if on:
            self.data[FLAGS_OFS + (i >> 3)] |= 1 << (i & 7)
        else:
            self.data[FLAGS_OFS + (i >> 3)] &= ~(1 << (i & 7)) & 0xFF

    def flags_set(self):
        return [i for i in range(1, FLAG_COUNT) if self.get_flag(i)]

    # ---------- moves ----------
    def skill(self, i):
        uses, flag = struct.unpack_from('<IB', self.data, ABIL_OFS + i * 8)
        learned = bool(flag & 1)
        if i == 10:
            learned = learned and bool(self.data[FLAGS_OFS + 7] & 1)
        if i == 11:
            learned = learned and bool(self.data[FLAGS_OFS + 7] & 2)
        return uses, learned

    def wheel(self):
        return list(self.data[SKILL_WHEEL_OFS:SKILL_WHEEL_OFS + SKILL_WHEEL_COUNT])

    def learn_skill(self, i):
        if i not in PUBLIC_SKILLS:
            raise ValueError(f'Move {i} is not a supported move ({PUBLIC_SKILLS})')
        if i == 10:
            self.data[FLAGS_OFS + 7] |= 1
        if i == 11:
            self.data[FLAGS_OFS + 7] |= 2
        ofs = ABIL_OFS + i * 8 + 4
        if self.data[ofs] & 1:
            return
        self.data[ofs] |= 1
        if i in WHEEL_SKILLS:
            w = SKILL_WHEEL_OFS
            wheel = self.data[w:w + 8]
            if i not in wheel and 0 in wheel:
                self.data[w + wheel.index(0)] = i

    def forget_skill(self, i):
        """Unlearn a move: clears it, takes it off the move wheel and switches off the extras that need it
        (e.g. its food boost, Dive and the Surf food boost for Surf). The use counter is kept."""
        if i not in PUBLIC_SKILLS:
            raise ValueError(f'Move {i} is not a supported move ({PUBLIC_SKILLS})')
        self.data[ABIL_OFS + i * 8 + 4] &= 0xFE
        if i == 10:
            self.data[FLAGS_OFS + 7] &= 0xFE
        if i == 11:
            self.data[FLAGS_OFS + 7] &= 0xFD
        w = SKILL_WHEEL_OFS
        for k in range(SKILL_WHEEL_COUNT):
            if self.data[w + k] == i:
                self.data[w + k] = 0
        gone = {key for key, (_, _, move, _) in EXTRAS.items() if move == i}
        gone |= {key for key, (_, _, _, other) in EXTRAS.items() if other in gone}
        for key in gone:
            for f in EXTRAS[key][1]:
                self.set_flag(f, False)

    def set_skill_slot(self, slot, move):
        if not 0 <= slot < SKILL_WHEEL_COUNT:
            raise ValueError('Wheel slot out of range')
        if move and not (move in WHEEL_SKILLS and self.skill(move)[1]):
            raise ValueError('Choose a learned wheel move or leave the slot empty')
        w = SKILL_WHEEL_OFS
        cur = self.data[w + slot]
        if cur == move:
            return
        if move:
            for k in range(SKILL_WHEEL_COUNT):
                if k != slot and self.data[w + k] == move:
                    self.data[w + k] = cur  # swap
        self.data[w + slot] = move

    # ---------- move extras (food boosts, Dive, Liquid Absorption) ----------
    def extra(self, key):
        return all(self.get_flag(f) for f in EXTRAS[key][1])

    def extra_blocker(self, key):
        """Why this extra cannot be unlocked yet, or '' if it can."""
        _, _, move, other = EXTRAS[key]
        if not self.skill(move)[1]:
            return f'Learn {name_of(SKILL_NAMES, move, "Move")} first'
        if other and not self.extra(other):
            return f'Unlock {EXTRAS[other][0]} first'
        return ''

    def set_extra(self, key, on=True):
        if key not in EXTRAS:
            raise ValueError(f'Unknown unlock {key!r} ({", ".join(EXTRAS)})')
        if on:
            why = self.extra_blocker(key)
            if why:
                raise ValueError(why + '.')
        for f in EXTRAS[key][1]:
            self.set_flag(f, on)

    # ---------- emotes (the game calls them reactions) ----------
    def reaction_learned(self, i):
        return bool(self.data[REACT_OFS + i] & 1)

    def reactions_learned(self):
        return [i for i in range(REACT_COUNT) if self.reaction_learned(i)]

    def reaction_wheel(self):
        return [self.data[REACT_WHEEL_OFS + k * 2] for k in range(REACT_WHEEL_COUNT)]

    def learn_reaction(self, i):
        if i not in PUBLIC_REACTIONS:
            raise ValueError('Choose an emote from the list')
        if self.reaction_learned(i):
            return
        self.data[REACT_OFS + i] |= 1
        wheel = self.reaction_wheel()
        if i not in wheel and 0 in wheel:
            k = wheel.index(0)
            self.data[REACT_WHEEL_OFS + k * 2] = i
            self.data[REACT_WHEEL_OFS + k * 2 + 1] = 0

    # ---------- item catalog (read only for normal items) ----------
    def catalog_state(self, item_id):
        """Raw catalog byte for an item (0 = never obtained). Read only: the editor never writes it for normal items."""
        return self.data[CATALOG_OFS + item_id] if 0 < item_id < len(ITEM_NAMES) else 0

    def catalog_items(self):
        """Set of item IDs the item catalog marks as obtained (wardrobe entries excluded)."""
        base, wid = CATALOG_OFS, set(WARDROBE_IDS)
        blk = self.data[base:base + len(ITEM_NAMES)]
        return {i for i, v in enumerate(blk) if v and i and i not in wid}

    # ---------- wardrobe (outfits and hairstyles) ----------
    def wardrobe_owned(self, item_id):
        return self.data[CATALOG_OFS + item_id] != 0

    def wardrobe_available(self, item_id):
        """Owned, or available from the start without being stored."""
        return item_id in WARDROBE_DEFAULTS or self.wardrobe_owned(item_id)

    def wardrobe_unlocked(self):
        return [i for i in WARDROBE_IDS if self.wardrobe_owned(i)]

    def unlock_wardrobe(self, ids=None):
        """Mark outfits/hairstyles as owned (all of them by default). Entries already set are left alone."""
        for i in WARDROBE_IDS if ids is None else ids:
            if i not in WARDROBE_IDS:
                raise ValueError(f'{i} is not a wardrobe entry')
            if not self.wardrobe_owned(i):
                self.data[CATALOG_OFS + i] = WARDROBE_OWNED

    def lock_wardrobe(self, ids):
        """Mark outfits/hairstyles as not owned again. Starting outfits/hairstyles cannot be removed."""
        for i in ids:
            if i not in WARDROBE_IDS:
                raise ValueError(f'{i} is not a wardrobe entry')
            if i in WARDROBE_DEFAULTS:
                raise ValueError(f'{KNOWN_WARDROBE.get(i, i)} is available from the start and cannot be removed')
            self.data[CATALOG_OFS + i] = 0

    # ---------- collection: Pokédex, habitats, crafting recipes, cooking, photo frames/filters ----------
    def collection_state(self, kind, i):
        """0 = nothing, 1 = partial (Pokémon seen, habitat discovered, some ways to cook a dish), 2 = complete."""
        if i not in _COLLECTION_IDS[kind]:
            raise ValueError(f'{i} is not an entry of {COLLECTION_INFO[kind][0]}')
        d = self.data
        if kind == 'dex':
            v = d[DEX_OFS + i]
            return 2 if v & 3 == 3 else 1 if v & 8 else 0
        if kind == 'habitat':
            v = d[HABITAT_OFS + i * HABITAT_SIZE]
            return 2 if v & 2 else v & 1
        if kind == 'recipe':
            return 2 if d[RECIPE_OFS + i * RECIPE_SIZE + 4] & 2 else 0
        if kind == 'cooking':
            known = [d[COOK_OFS + r] & 1 for r in COOK_ROWS[i]]
            return 2 if all(known) else 1 if any(known) else 0
        if kind == 'item':
            return 2 if d[CATALOG_OFS + i] else 0
        if kind == 'record':
            return 2 if d[RECORD_OFS + i] & 1 else 0
        if kind == 'artifact':
            return 2 if d[ARTIFACT_OFS + i] & 1 else 0
        if kind == 'photoop':
            return 2 if d[PHOTOOP_OFS + i] & 1 else 0
        ofs = PHOTO_STYLE_OFS + (FRAME_COUNT if kind == 'filter' else 0)
        return 2 if d[ofs + i] & 1 else 0

    def collection_count(self, kind, state=2):
        return sum(self.collection_state(kind, i) >= state for i, _ in COLLECTION[kind])

    def unlock_collection(self, kind, ids=None, partial=False):
        """Complete entries (all of the kind by default). partial=True only marks a Pokémon seen / a habitat
        discovered. Only sets bits; entries already there are left alone. Returns how many entries changed."""
        if kind not in COLLECTION:
            raise ValueError(f'Unknown collection {kind!r} ({", ".join(COLLECTION)})')
        if partial and kind not in ('dex', 'habitat'):
            raise ValueError('Only Pokémon and habitats have a seen/discovered state')
        ids = [i for i, _ in COLLECTION[kind]] if ids is None else list(ids)
        d = self.data
        todo = [i for i in ids if self.collection_state(kind, i) < (1 if partial else 2)]
        order = 0
        if kind == 'recipe' and todo:
            order = max(struct.unpack_from('<H', d, RECIPE_OFS + k * RECIPE_SIZE + 2)[0] for k in range(RECIPE_COUNT))
            if order + len(todo) > 0xFFFF:
                raise ValueError('There is no room for more recipes in the learned order')
        for i in todo:
            if kind == 'dex':
                d[DEX_OFS + i] |= 8 if partial else 3
            elif kind == 'habitat':
                d[HABITAT_OFS + i * HABITAT_SIZE] |= 1 if partial else 3
            elif kind == 'recipe':
                order += 1
                o = RECIPE_OFS + i * RECIPE_SIZE
                struct.pack_into('<H', d, o + 2, order)
                d[o + 4] |= 2
            elif kind == 'cooking':
                for r in COOK_ROWS[i]:
                    d[COOK_OFS + r] |= 1
            elif kind == 'item':
                d[CATALOG_OFS + i] = CATALOG_OBTAINED
            elif kind == 'record':
                d[RECORD_OFS + i] |= 1
            elif kind == 'artifact':
                d[ARTIFACT_OFS + i] |= 1
                item = ARTIFACTS[i][0]
                if not d[CATALOG_OFS + item]:
                    d[CATALOG_OFS + item] = CATALOG_OBTAINED
            elif kind == 'photoop':
                d[PHOTOOP_OFS + i] |= 1
            else:
                d[PHOTO_STYLE_OFS + (FRAME_COUNT if kind == 'filter' else 0) + i] |= 1
        return len(todo)

    # ---------- quests ----------
    def quest_state(self, q):
        if not 0 <= q < QUEST_COUNT:
            raise ValueError(f'Quest must be 0-{QUEST_COUNT - 1}')
        return struct.unpack_from('<H', self.data, QUEST_OFS + 2 * q)[0]

    def quests_in(self, state):
        return [q for q in QUESTS if self.quest_state(q) == state]

    def set_quest_state(self, q, state):
        """Only the state number; nothing the quest does is applied (see complete_quest)."""
        if state not in QUEST_STATES:
            raise ValueError(f'Quest state must be one of {sorted(QUEST_STATES)}')
        self.quest_state(q)
        struct.pack_into('<H', self.data, QUEST_OFS + 2 * q, state)

    def _apply_effects(self, q, phase):
        """Carry out the parts of a quest's start or done commands that live in this file. Returns the command
        types left to the game (resident moves, map changes, events...)."""
        left = []
        for kind, v in quest_effects(q, phase):
            if kind in ('flag', 'unflag'):
                if 1 <= v < FLAG_COUNT:
                    self.set_flag(v, kind == 'flag')
            elif kind == 'move':
                if v in PUBLIC_SKILLS:
                    self.learn_skill(v)
                else:
                    left.append(QCMD_MOVE)
            elif kind == 'recipe':
                if v in _COLLECTION_IDS['recipe']:
                    self.unlock_collection('recipe', [v])
                else:
                    left.append(QCMD_RECIPE)
            else:
                left.append(v)
        return left

    def start_quest(self, q):
        """Mark a quest in progress and apply its start commands that live in this file."""
        self.set_quest_state(q, QUEST_ACTIVE)
        return self._apply_effects(q, 'start')

    def complete_quest(self, q, rewards=True):
        """Mark a quest done. With rewards, also apply its start commands (when it had not started) and its done
        commands: flags, moves and crafting recipes. Returns the command types only the game can carry out."""
        before = self.quest_state(q)
        self.set_quest_state(q, QUEST_DONE)
        if not rewards or before == QUEST_DONE:
            return []
        left = self._apply_effects(q, 'start') if before < QUEST_ACTIVE else []
        return left + self._apply_effects(q, 'done')

    # ---------- upgrades and features (function flags) ----------
    def upgrade(self, key):
        return all(self.get_flag(f) for f in UPGRADES[key][1])

    def set_upgrade(self, key, on=True):
        """Switch an upgrade on (with the ones it builds on) or off (with the ones that build on it)."""
        if key not in UPGRADES:
            raise ValueError(f'Unknown upgrade {key!r} ({", ".join(UPGRADES)})')
        if on:
            need = UPGRADES[key][2]
            if need:
                self.set_upgrade(need, True)
        else:
            for other, (_, _, need) in UPGRADES.items():
                if need == key and self.upgrade(other):
                    self.set_upgrade(other, False)
        for f in UPGRADES[key][1]:
            self.set_flag(f, on)

    # ---------- Life Coins ----------
    @property
    def coins(self):
        return struct.unpack_from('<i', self.data, COINS_OFS)[0]

    @coins.setter
    def coins(self, value):
        if not 0 <= value <= COINS_MAX:
            raise ValueError(f'Life Coins must be 0-{COINS_MAX:,}')
        struct.pack_into('<i', self.data, COINS_OFS, value)

    def forget_reaction(self, i):
        """Unlearn an emote and take it off the emote wheel."""
        if i not in PUBLIC_REACTIONS:
            raise ValueError('Choose an emote from the list')
        self.data[REACT_OFS + i] &= 0xFE
        for k in range(REACT_WHEEL_COUNT):
            if self.data[REACT_WHEEL_OFS + k * 2] == i:
                self.data[REACT_WHEEL_OFS + k * 2:REACT_WHEEL_OFS + k * 2 + 2] = b'\0\0'

    def set_reaction_slot(self, slot, emote):
        if not 0 <= slot < REACT_WHEEL_COUNT:
            raise ValueError('Wheel slot out of range')
        if emote and not (emote in PUBLIC_REACTIONS and self.reaction_learned(emote)):
            raise ValueError('Choose a learned emote or leave the slot empty')
        w = REACT_WHEEL_OFS
        if self.data[w + slot * 2] == emote:
            return
        for k in range(REACT_WHEEL_COUNT):
            if emote and k != slot and self.data[w + k * 2] == emote:
                a, b = w + slot * 2, w + k * 2  # move both saved bytes with the emote
                pa, pb = bytes(self.data[a:a + 2]), bytes(self.data[b:b + 2])
                self.data[a:a + 2], self.data[b:b + 2] = pb, pa
                return
        self.data[w + slot * 2] = emote
        self.data[w + slot * 2 + 1] = 0


def _diff_patches(old, new, page=4096):
    """[(offset, old_bytes, new_bytes)] for every differing run. Fast: only differing 4 KB pages are scanned."""
    out = []
    for p in range(0, len(new), page):
        a, b = old[p:p + page], new[p:p + page]
        if a == b:
            continue
        i, n = 0, len(a)
        while i < n:
            if a[i] != b[i]:
                j = i + 1
                while j < n and a[j] != b[j]:
                    j += 1
                out.append((p + i, bytes(a[i:j]), bytes(b[i:j])))
                i = j
            else:
                i += 1
    return out


def describe_changes(a, b, limit=400):
    """Human readable list of what differs going from save `a` to save `b` (both CommonSave)."""
    out = []
    if a.player_name != b.player_name:
        out.append(f'Player name: {a.player_name} -> {b.player_name}')
    pa, pb = a.play_seconds, b.play_seconds
    if pa is not None and pb is not None and int(pa) != int(pb):
        out.append(f'Play time: {fmt_playtime(pa)} -> {fmt_playtime(pb)}')
    for i in range(INV_COUNT):
        (ia, ca, _), (ib, cb, _) = a.get_slot(i), b.get_slot(i)
        if (ia, ca) != (ib, cb):
            fa = f'{item_name(ia)} x{ca}' if ia else 'empty'
            fb = f'{item_name(ib)} x{cb}' if ib else 'empty'
            out.append(f'Bag slot {i}: {fa} -> {fb}')
    va, vb = set(a.villagers()), set(b.villagers())
    for i in sorted(vb - va):
        out.append(f'New resident: {name_of(VILLAGER_NAMES, i, "Resident")}')
    for i in sorted(va - vb):
        out.append(f'Resident gone: {name_of(VILLAGER_NAMES, i, "Resident")}')
    for i in sorted(va & vb):
        x, y = a.get_villager(i), b.get_villager(i)
        for key, label in (('friendship', 'friendship'), ('thank_points', 'thank points'), ('present_level', 'present level'),
                           ('name_talk_done', 'name talk done'), ('home_area_name', 'home area')):
            if x[key] != y[key]:
                out.append(f'{x["name"]}: {label} {x[key] or "-"} -> {y[key] or "-"}')
    for i in PUBLIC_SKILLS:
        if a.skill(i)[1] != b.skill(i)[1]:
            out.append(f'Move {name_of(SKILL_NAMES, i, "Move")}: {"learned" if b.skill(i)[1] else "forgotten"}')
    if a.wheel() != b.wheel():
        fmt = lambda w: ', '.join(name_of(SKILL_NAMES, m, 'Move') if m else '-' for m in w)
        out.append(f'Move wheel: [{fmt(a.wheel())}] -> [{fmt(b.wheel())}]')
    for i in range(REACT_COUNT):
        if a.reaction_learned(i) != b.reaction_learned(i):
            out.append(f'Emote {name_of(REACTION_NAMES, i, "Emote")}: {"learned" if b.reaction_learned(i) else "forgotten"}')
    if a.reaction_wheel() != b.reaction_wheel():
        out.append('Emote wheel layout changed')
    wa, wb = a.wardrobe_unlocked(), b.wardrobe_unlocked()
    if wa != wb:
        def names(ids):
            n = [KNOWN_WARDROBE.get(i, f'entry {i}') for i in ids]
            return ', '.join(n[:6]) + (f' and {len(n) - 6} more' if len(n) > 6 else '')
        new = [i for i in wb if i not in wa]
        gone = [i for i in wa if i not in wb]
        out.append(f'Outfits & hairstyles: {len(wa)} -> {len(wb)} of {len(WARDROBE_IDS)} unlocked'
                   + (f' (new: {names(new)})' if new else '') + (f' (removed: {names(gone)})' if gone else ''))
    if a.coins != b.coins:
        out.append(f'Life Coins: {a.coins:,} -> {b.coins:,}')
    for kind, entries in COLLECTION.items():
        title, _, full = COLLECTION_INFO[kind]
        ch = [(n, b.collection_state(kind, i)) for i, n in entries
              if a.collection_state(kind, i) != b.collection_state(kind, i)]
        if ch:
            done = [n for n, y in ch if y == 2]
            other = len(ch) - len(done)
            more = f' and {len(done) - 6} more' if len(done) > 6 else ''
            out.append(f'{title}: {a.collection_count(kind)} -> {b.collection_count(kind)} of {len(entries)} {full}'
                       + (f' (new: {", ".join(done[:6])}{more})' if done else '')
                       + (f' ({other} other state change{"s" if other != 1 else ""})' if other else ''))
    for q in sorted(QUESTS):
        sa, sb = a.quest_state(q), b.quest_state(q)
        if sa != sb:
            name = quest_name(q)
            out.append(f'Quest {q}{f" ({name})" if name else ""}: {QUEST_STATES.get(sa, sa)} -> {QUEST_STATES.get(sb, sb)}')
    for i in range(1, FLAG_COUNT):
        if a.get_flag(i) != b.get_flag(i):
            out.append(f'Flag {i} ({KNOWN_FLAGS.get(i, "unknown")}): {"on" if b.get_flag(i) else "off"}')
    if len(out) > limit:
        out = out[:limit] + [f'... and {len(out) - limit} more']
    return out


class SaveFolder:
    REL = os.path.join('G00', 'CMNDAT.BIN')

    def __init__(self, folder):
        folder = os.path.abspath(folder)
        if os.path.basename(folder).upper() in ('G00', 'B00', 'S00'):
            folder = os.path.dirname(folder)
        if not os.path.isfile(os.path.join(folder, self.REL)):
            raise FormatError('Pick the save folder that contains G00 (and S00), e.g. ...\\0400A3A01EE4C000')
        self.folder = folder
        self.common = CommonSave(os.path.join(folder, self.REL))
        self.islands = {}            # area -> pokopia_island.Island opened for editing
        self.order, self.redo_order = [], []   # undo history across CMNDAT ('c') and islands (area numbers)

    # ---------- one undo history for the common save and the islands ----------
    @property
    def edited(self):
        return self.common.edited or any(i.edited for i in self.islands.values())

    def edited_islands(self):
        return [i for i in self.islands.values() if i.edited]

    def note_commit(self, key):
        """Record that an edit was committed to the common save ('c') or to island `key`."""
        self.order.append(key)
        self.redo_order.clear()
        self.common._redo.clear()
        for isl in self.islands.values():
            isl._redo.clear()

    def undo(self):
        """Undo the most recent edit anywhere. Returns (key, label) or None."""
        while self.order:
            key = self.order.pop()
            label = self.common.undo() if key == 'c' else (self.islands[key].undo() if key in self.islands else None)
            if label:
                self.redo_order.append(key)
                return key, label
        return None

    def redo(self):
        while self.redo_order:
            key = self.redo_order.pop()
            label = self.common.redo() if key == 'c' else (self.islands[key].redo() if key in self.islands else None)
            if label:
                self.order.append(key)
                return key, label
        return None

    def history(self):
        """Labels of every edit not saved yet, oldest first."""
        seen, out = {}, []
        for key in self.order:
            n = seen.get(key, 0)
            seen[key] = n + 1
            h = self.common.history if key == 'c' else (self.islands[key].history if key in self.islands else [])
            lab = h[n] if n < len(h) else '?'
            out.append(lab if key == 'c' else f'{self.islands[key].name}: {lab}')
        return out

    def pending_changes(self):
        lines = self.common.pending_changes() if self.common.edited else []
        for isl in self.edited_islands():
            lines += isl.summary()
        return lines

    def game_backup(self):
        """The game's own previous save (B00), or None."""
        p = os.path.join(self.folder, 'B00', 'CMNDAT.BIN')
        try:
            return CommonSave(p) if os.path.isfile(p) else None
        except FormatError:
            return None

    def stage_files(self):
        """{area number: path} for every G00/STGDAT##.BIN."""
        out = {}
        g = os.path.join(self.folder, 'G00')
        for fn in sorted(os.listdir(g)):
            u = fn.upper()
            if len(u) == 12 and u.startswith('STGDAT') and u.endswith('.BIN') and u[6:8].isdigit():
                out[int(u[6:8])] = os.path.join(g, fn)
        return out

    def photo_file(self):
        p = os.path.join(self.folder, 'G00', 'SCSHDAT.BIN')
        return p if os.path.isfile(p) else None

    def changed_on_disk(self):
        """True if the game (or anything else) rewrote CMNDAT.BIN, or an island being edited, since it was opened."""
        try:
            with open(self.common.path, 'rb') as f:
                if f.read() != self.common.original:
                    return True
        except OSError:
            return True
        return any(isl.changed_on_disk() for isl in self.edited_islands())

    def write(self, out_folder=None, in_place=False, backup_root=None):
        """Write to a new folder (default) or in place after an automatic backup. Returns (path, backup)."""
        if in_place and self.changed_on_disk():
            raise ValueError('The save on disk changed after it was opened (the game saved again). Reopen it first.')
        new_bytes = self.common.to_bytes()
        # validate what we are about to write
        _validate_bytes(new_bytes, bytes(self.common.data))
        island_bytes = []
        for isl in self.edited_islands():
            blob = isl.to_bytes()
            isl.validate(blob)
            island_bytes.append((isl, blob))
        backup = None
        if in_place:
            ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_root = backup_root or default_backup_root()
            backup = os.path.join(backup_root, 'auto_' + ts)
            shutil.copytree(self.folder, backup)
            target = self.folder
        else:
            if not out_folder:
                raise ValueError('Output folder required')
            out_folder = os.path.abspath(out_folder)
            if os.path.normcase(out_folder) == os.path.normcase(self.folder):
                raise ValueError('Output folder is the input folder. Use in-place mode instead.')
            if os.path.exists(out_folder) and os.listdir(out_folder):
                raise ValueError('Output folder must be new or empty')
            shutil.copytree(self.folder, out_folder, dirs_exist_ok=True)
            target = out_folder
        dst = os.path.join(target, self.REL)
        tmpf = dst + '.tmp'
        with open(tmpf, 'wb') as f:
            f.write(new_bytes)
        os.replace(tmpf, dst)
        # re-read from disk and compare
        again = CommonSave(dst)
        if bytes(again.data) != bytes(self.common.data):
            raise FormatError('Verification after write failed')
        for isl, blob in island_bytes:
            dst = os.path.join(target, 'G00', os.path.basename(isl.path))
            tmpf = dst + '.tmp'
            with open(tmpf, 'wb') as f:
                f.write(blob)
            os.replace(tmpf, dst)
            with open(dst, 'rb') as f:
                isl.validate(f.read())
        return target, backup


def default_backup_root():
    return os.path.join(os.path.expanduser('~'), 'Documents', 'Pokopia_Save_Backups')


def _validate_bytes(b, expected_data):
    length = struct.unpack_from('<I', b, 0x10)[0]
    raw = zlib.decompress(b[HEADER_SIZE:length])
    if raw != expected_data or struct.unpack_from('<I', b, 0)[0] != MAGIC:
        raise FormatError('Re-encoded save failed validation, nothing written')


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()
