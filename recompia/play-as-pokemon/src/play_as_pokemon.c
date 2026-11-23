/* Play as Pokemon for Recompia (Modtopia code mod). GPL-3.0-or-later.
 *
 * The same mod as the emulator version (mods/play-as-pokemon: an IPS patch plus a cheat file), rebuilt on Modtopia:
 * every code patch of the IPS is a take_over hook point here (mod.toml), and the cheat's button combos and memory writes
 * run in the player's per-frame hook with the player's pad (pad_read). All offsets are for game 2.0.1 (main build
 * 76a489f3bd3642fa), the same build the emulator version targets.
 *
 * The state the IPS kept in the game's memory (main+0x3D14C00..) lives in this library instead:
 *   g_form       the form the player is turned into (a character-definition ID, 0 = not transformed)
 *   g_holds      the animation packages and motion sets this mod holds for the player's forms (1.6, see "holds")
 *   g_load       the form whose animations are loading: it is requested once they are (1.6)
 *
 * Hook points (see mod.toml and re/build/build_v06.py / build_v07.py for the original patches):
 *   form_get       desired-form getter: returns g_form while transformed
 *   form_set       desired-form setter: stores g_form while transformed
 *   request_state  RequestState: drops the request for state 1 (human) while transformed
 *   probe          animation condition 0x56 (wall probe): true for the player while transformed (no stretch / flashing)
 *   to_human       the game's "turn the player human for an interaction" (talking): noted, the player turns back after it
 *   char_setup     the character's model setup: a player's model in one of this mod's forms is built only once the form's
 *                  animations are loaded (1.6), else as the human for the moment
 *   player_tick    the player's update: buttons, loading a form's animations before asking for it, flying, the Pokemon's
 *                  ability (Grow, Burn, Water), and turning the player back into the Pokemon when the game changed the form
 *                  some other way (talking to a Pokemon)
 *   motion_reset   the world reset's "release every motion set" (1.5): the mod forgets the animations it had loaded
 *
 * Every hook acts on the player's own character only. In Link Play the other players are characters of the same kind, and
 * RequestState runs for every character, so without that check a transformed player's game would also keep the others from
 * turning back and hand them its own form.
 *
 * Link Play (1.4): the game sends each player's wanted form to the others, but a game only turns another player into the
 * game's own six player forms (it plays that form's transformation action). So player_tick, char_setup and probe also act on
 * the other players' characters while they are in one of this mod's forms: see "Link Play" below.
 */
#include <modtopia/modtopia.h>

#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#ifdef _WIN32
#include <windows.h>
#elif !defined(PAP_SWITCH)
#include <time.h>
#endif

#include "forms.h"

MT_DECLARE_MOD()

/* The Switch / emulator build fills two unused game functions; the first is full, so these helpers go to the second
   (build_emulator.py places .text2.* there). Nothing on Recompia. */
#ifdef PAP_SWITCH
#define CAVE2_FN __attribute__((section(".text2.moved")))
#else
#define CAVE2_FN
#endif

/* ---------------------------------------------------------------- game offsets (main-relative, 2.0.1) */
#define PLAYER_GLOBAL 0x3561928ull   /* [[main+0x3561928] + 0x30] = the player character */
#define ENTITY_TABLE  0x356A778ull   /* [[main+0x356A778] + 0x58] = the player's entity */
#define MGR_GLOBAL    0x3561738ull   /* [main+0x3561738] + 0x8C830 = the animation package manager */
#define MOTION_DAT    0x35619E8ull   /* [main+0x35619E8] = the motion-set table (+0x18 entries, +0x20 count, +0x22 used) */
#define FN_MSET_ACQ   0x8D11C0ull    /* (x0, w1 resource): acquire a motion set, binding its animations on the first use */
#define FN_MSET_REL   0x8D1380ull    /* (x0, w1 resource, w2 0): release it */
#define FN_PKG_REQ    0x8D20A0ull    /* (mgr, w1 package): request an animation package */
#define FN_PKG_READY  0x8D1130ull    /* (mgr, w1 package) -> w0 1 when loaded */
#define FN_PKG_REL    0x8D2420ull    /* (mgr, w1 package, w2 0): release it */
#define MGR_OFFSET    0x8C830ull
#define PKG_MAP       0x4E08ull      /* mgr + 0x4E08: u16 package per resource ID */
#define GAME_MGR      0x3561710ull   /* [main+0x3561710] = the game manager: +0x8C its permission mask, 0 until the world is up */
#define GM_PERMISSIONS 0x8C

/* player character */
#define P_STATE       0x3778   /* the state machine RequestState gets (x0) */
#define P_FORM_NOW    0x5A44   /* u16 current form */
#define P_FORM_WANT   0x5A46   /* u16 desired form */
#define P_REQ_STATE   0x3788   /* u16 pending state */
#define P_REQ_ANIM    0x378A   /* u16 transition animation */
#define P_REQ_GO      0x378C   /* u8 request */
#define P_ISDITTO     0x378D   /* u8 set by the game for every form but the human */
#define TRANSFORM_ANIM 0x3B2
#define HUMAN 1
#define HUMAN_RES 1    /* the human model's animation resource: the game's own, never loaded or released by the mod */
#define FORM_MAX 1000  /* the player update applies a pending state 1..1000 */

/* character definitions (1.6): the record of a form, as the model setup (main+0x27CAD0) and main+0x276764 find it */
#define DB_GLOBAL     0x35618F0ull   /* [main+this] = the game's data tables: +0x2B70 how many, table i at +0x10 + 8 * i */
#define DEF_TABLE     0x7B0          /* the character definitions, table 0xF6 (the game takes table 0 when there are fewer) */
#define DEF_DEFAULT   0x35B63C0ull   /* main+this = the data of a record that has none of its own (record +8 = 0) */
#define DEF_MODEL_PKG 0xC6           /* u16 the model's package: the model build (main+0x69DBE0) builds nothing until it is loaded */
#define DEF_RES       0xD8           /* u16 the animation resource (motion set) */
#define PKG_MAX       0x3FF          /* package ids 1..0x3FF */

/* player entity (flying) */
#define E_MOTION 0x228   /* current motion record */
#define E_MSET   0x260   /* motion set: +0xC8 records, +0xD0 count */
#define E_VY     0xBCC   /* vertical speed, cm per frame */
#define E_Y      0xBE4   /* height */
#define MOTION_IDLE  1
#define MOTION_HOVER 7
#define INFO_FLYING  0x22

/* abilities (1.3) */
#define FN_GROW       0x1F1200ull    /* (farm, s16 cell[3]) -> w0 1: crops and plants in a plus shape around the cell grew a stage */
#define FN_OBJECT_ACT 0x77CEA0ull    /* (objects, u16 *by, x, y, z, w5 0) -> bit 0: the object placed at the cell reacted (vfunc 0x118: burn) */
#define FIELD         0x35616F8ull   /* [main+this] = the field manager; + FARM = its crops and plants */
#define FARM          0x11058ull
#define OBJECTS       0x35616F0ull   /* [main+this] = the placed objects */
#define P_ACTIONS     0x18B8         /* the player's action controller; its +0x984 = the action playing (u16) */
#define A_CURRENT     0x984
#define P_ID          0x27FE         /* u16 the character's id */
#define VF_POSITION   0x140          /* player vfuncs: position (q0 = x, y, z), yaw (s0, radians), request an action */
#define VF_YAW        0x18
#define VF_REQUEST    0x338
#define ACT_BURN      700            /* the residents' specialty actions: on the player they play the animation only */
#define ACT_WATER     703
#define ACT_GROW      706
#define FN_WATER      0x3694C0ull    /* (&cell, power 1, by the player 1, 0, waterer's id, 0) -> w0 1: soil / plants / basin watered (Water Gun's) */
#define BURN_HANDLER  120            /* the Burn action's handler: what a resident's Burn passes as w5 (object vfunc 0x118) */
#define POWER_HANDLER 122            /* Generate's (action 709): w5 'z' = object vfunc 0x120, a light or machine is powered */
#define BUBBLE_HANDLER 121           /* action 705's handler: Water's Bubble, 13 cells around the target (sludge, crops) */
#define FN_BUBBLE     0x5A60E0ull    /* its execute (handler, controller, args): the owner must be a town Pokemon */
#define ACT_GENERATE  709
#define ACT_BUBBLE    705            /* a resident's Bubble: the animation for it */
#define ACT_HUMAN_ZR  881            /* what the game starts on ZR when isDitto is 0 (an emote-like motion on a Pokemon): see "interacting" */
#define FN_END_ACTION 0x27E804ull    /* (action controller, 1) the game's cancel of the action playing (what its cancel vfunc 0x27E770, e.g. a
                                        jump, does): the owner's vfunc 0xC0, the handlers' end, the controller's action 0 */
#define FN_HAS_LAYER  0x38DF8ull     /* (world, &u8 kind, &cell) -> 1: the cell holds a block of that kind (a query) */
#define WORLD         0x34EFC98ull   /* [main+this] = the world's blocks */
#define SLUDGE        8              /* the block kind Bubble works on (the sludge on Bleak Beach) */
#define RESIDENT_IDS  0x2            /* a character id's top nibble: 1 players, 2 the town's Pokemon */
#define PLAYER_IDS    0x1
#define SLOT          0x3D14D00ull   /* unused bss (the crafting range mod uses +0xE00): the test slot, and the cell passed to the game */
#define SLOT_MAGIC    0x42414B50u    /* "PKAB" */

/* ---------------------------------------------------------------- state */
static const MtHost *H;
static MtMod *M;
static uint64_t MAIN;

#ifdef PAP_SWITCH
/* The Switch / emulator build (mods/play-as-pokemon/src/build_emulator.py) keeps these two where the Pokopia Editor's live controls
   and the Pokemon-choice cheat find them: u16 main+0x3D14C00 the form held, u16 main+0x3D14C06 the chosen Pokemon (0: the default). */
extern _Atomic uint16_t pap_form, pap_selected;
#define g_form pap_form
#define g_selected pap_selected
#else
static _Atomic uint16_t g_form;        /* read by hooks on any game thread */
#endif
static uint16_t g_load;                /* the player's own thread only (update, model setup): the form waiting for its animations */
static uint64_t g_load_since;
#ifndef PAP_SWITCH
static _Atomic uint16_t g_selected = DEFAULT_FORM;   /* what the combo turns the player into */
#endif
static _Atomic int g_settings_changed;
static _Atomic int g_fly = 1, g_cycle = 1, g_messages = 1;
static _Atomic int g_fly_top = 400;   /* the top climbing / descending speed, cm per second (setting fly_speed) */
enum { AB_GROW, AB_BURN, AB_WATER, AB_GENERATE, AB_KINDS };
#ifndef PAP_SWITCH
static const char *const AB_NAMES[] = {"Grow", "Burn", "Water", "Generate"};
#endif
static _Atomic int g_abilities = 1, g_ability = -1;   /* -1: the Pokemon's own (ABILITY_OF) */
static _Atomic int g_interact = 1;   /* doors, the crafting bench, the bag and building while transformed (1.7) */
static uint32_t g_prev_buttons;
static int g_prev_key_on, g_prev_key_off, g_prev_key_ability;
enum { PRESS_NONE, PRESS_ZR, PRESS_COMBO, PRESS_KEY };
static int g_ab_press;   /* the ability button pressed this frame (buttons), used by abilities() */
/* Everything timed is in milliseconds, never in frames: Recompia's frame rate is whatever the player set (60, 120, unlimited). */
#define REQUEST_GAP_MS   700   /* least time between two form requests */
#define SETTLED_MS       250   /* how long the last form change must have been complete */
#define REQUEST_MAX_MS  3000   /* a form change that never settles does not block the next one for longer */
#define CYCLE_PAUSE_MS   350   /* ZL + D-pad Left / Right: transform once the player stops flicking through the list */
#define DROP_HOLD_MS     120   /* ZL + ZR held this long = drop (a shorter overlap is a change of direction) */
#define LAND_STILL_MS     70   /* descending without losing height for this long = standing on something */
#define HOP_MS            50   /* the landing hop */
#define REVERT_WAIT_MS   500   /* the game changed the form: let its own change finish this long before turning back */
#define REVERT_LIMIT       3   /* turn back at most this often within REVERT_WINDOW_MS, then leave the form as the game wants it */
#define REVERT_WINDOW_MS 20000
#define INTERACTION_QUIET_MS 1000   /* an interaction is over once the game stopped asking for the human form this long ... */
#define WALK_MS           250   /* ... and the player has walked (left stick past WALK_STICK) this long */
#define WALK_STICK      12000
static _Atomic uint64_t g_interaction_at;   /* the game's last "turn the player human for an interaction" while transformed (0 = none) */
static uint64_t g_interaction_start, g_walk_since;
static int16_t g_lx, g_ly;                  /* the left stick, as buttons() last read it */
static int g_want = -1;                 /* the form to turn into once the last change is done (0 = human, -1 = nothing waiting) */
static uint64_t g_want_after;           /* not before this time */
static uint64_t g_last_request, g_settled_since;
static int g_zr_was, g_takeoff, g_descending;
static uint64_t g_both_since, g_still_since, g_hop_until;
static float g_ref_y;
static uint64_t g_wrong_since, g_revert_window;   /* keep_form */
static int g_reverts;

static uint64_t now_us(void) {
#ifdef _WIN32
    static LARGE_INTEGER f;
    LARGE_INTEGER c;
    if (!f.QuadPart) QueryPerformanceFrequency(&f);
    QueryPerformanceCounter(&c);
    return (uint64_t)(c.QuadPart / f.QuadPart) * 1000000 + (uint64_t)(c.QuadPart % f.QuadPart) * 1000000 / (uint64_t)f.QuadPart + 1;
#elif defined(PAP_SWITCH)
    uint64_t c, f;
    __asm__ volatile("mrs %0, cntpct_el0" : "=r"(c));
    __asm__ volatile("mrs %0, cntfrq_el0" : "=r"(f));
    if (!f) f = 19200000;
    return c / f * 1000000 + c % f * 1000000 / f + 1;
#else
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return (uint64_t)t.tv_sec * 1000000 + (uint64_t)t.tv_nsec / 1000 + 1;
#endif
}
static uint64_t now_ms(void) { return now_us() / 1000 + 1; }

/* ---------------------------------------------------------------- guest memory */
static int rd(uint64_t a, void *out, size_t n) { return a && H->mem_read(a, out, n) == MT_OK; }
static uint64_t r64(uint64_t a) { uint64_t v = 0; return rd(a, &v, 8) ? v : 0; }
static int r16(uint64_t a, uint16_t *v) { return rd(a, v, 2); }
static void w8(uint64_t a, uint8_t v) { H->mem_write(a, &v, 1); }
static void w16(uint64_t a, uint16_t v) { H->mem_write(a, &v, 2); }
static void w64(uint64_t a, uint64_t v) { H->mem_write(a, &v, 8); }
static void wf(uint64_t a, float v) { H->mem_write(a, &v, 4); }

static uint64_t player(void) {
    uint64_t g = r64(MAIN + PLAYER_GLOBAL);
    return g ? r64(g + 0x30) : 0;
}
/* 1 when a hooked function is working on the player's own character (x0 = the character) */
static int is_player(uint64_t obj) {
    uint64_t P = player();
    return P && obj == P;
}
static uint64_t pkg_mgr(void) {
    uint64_t g = r64(MAIN + MGR_GLOBAL);
    return g ? g + MGR_OFFSET : 0;
}
static uint16_t pkg_of(uint64_t mgr, uint16_t res) {
    uint16_t p = 0;
    r16(mgr + PKG_MAP + (uint64_t)res * 2, &p);
    return p;
}
static uint64_t call(uint64_t fn, uint64_t x0, uint64_t x1, uint64_t x2) {
    MtCall c;
    memset(&c, 0, sizeof c);
    c.x[0] = x0, c.x[1] = x1, c.x[2] = x2;
    if (H->call_guest(MAIN + fn, &c) != MT_OK) return 0;
    return c.x[0];
}
static uint64_t call_at(uint64_t addr, uint64_t x0, uint64_t x1) {   /* a guest function by its address (a vfunc) */
    MtCall c;
    memset(&c, 0, sizeof c);
    c.x[0] = x0, c.x[1] = x1;
    if (!addr || H->call_guest(addr, &c) != MT_OK) return 0;
    return c.x[0];
}
static uint64_t vfunc(uint64_t obj, uint32_t off) {
    uint64_t vt = r64(obj);
    return vt ? r64(vt + off) : 0;
}
/* The game's animation package and motion set functions keep plain counts. The mod calls them from several game threads at once
   (each player's update and model setup can run on its own worker), so its calls go one at a time. */
static atomic_flag g_game_lock = ATOMIC_FLAG_INIT;
static void spin_pause(void) {
#if defined(__x86_64__) || defined(__i386__)
    __builtin_ia32_pause();
#elif defined(__aarch64__)
    __asm__ volatile("yield");
#endif
}
static uint64_t game_call(uint64_t fn, uint64_t x0, uint64_t x1, uint64_t x2) {
    while (atomic_flag_test_and_set_explicit(&g_game_lock, memory_order_acquire)) spin_pause();
    uint64_t r = call(fn, x0, x1, x2);
    atomic_flag_clear_explicit(&g_game_lock, memory_order_release);
    return r;
}
/* The motion set of a resource as FN_MSET_ACQ finds it (0 when it has none). */
static uint64_t motion_set(uint16_t res) {
    uint64_t dat = r64(MAIN + MOTION_DAT);
    uint16_t n = 0, used = 0;
    if (!dat || !r16(dat + 0x20, &n) || !r16(dat + 0x22, &used) || !n || !used) return 0;
    uint64_t table = r64(dat + 0x18);
    for (uint32_t i = 0, seen = 0; i < n && seen < used; i++) {
        uint64_t e = r64(table + 8ull * i);
        int32_t id = 0;
        if (!e || !rd(e + 8, &id, 4) || id < 0) continue;
        if (id == res) return r64(e);
        seen++;
    }
    return 0;
}
static int motion_set_uses(uint64_t set) {   /* -1: no set, or not loaded (FN_MSET_ACQ / REL then do nothing) */
    uint8_t loaded = 0;
    uint16_t count = 0;
    if (!set || !rd(set + 0x1076, &loaded, 1) || !loaded || !r16(set + 0x1074, &count)) return -1;
    return count;
}

/* A form's definition record, found as the game's model setup finds it: vfunc 0x38(0) of the definitions table, then its
   vfunc 0x30(form). 0 when the tables are not up. */
static uint64_t def_record(uint16_t form) {
    uint64_t db = r64(MAIN + DB_GLOBAL), tbl, sub;
    uint32_t n = 0;
    if ((uint16_t)(form - 1) >= FORM_MAX || !db || !rd(db + 0x2B70, &n, 4)) return 0;
    tbl = r64(db + (n < 0xF7 ? 0 : DEF_TABLE) + 0x10);
    sub = tbl ? call_at(vfunc(tbl, 0x38), tbl, 0) : 0;
    return sub ? call_at(vfunc(sub, 0x30), sub, form) : 0;
}
static uint64_t def_data(uint64_t rec) {
    uint64_t d = r64(rec + 8);
    return d ? d : MAIN + DEF_DEFAULT;
}

/* ---------------------------------------------------------------- forms */
#ifndef PAP_SWITCH   /* names: for the log, the messages and the menu, which a Switch does not have */
static const char *form_name(uint16_t id) {
    for (int i = 0; i < FORM_COUNT; i++)
        if (FORMS[i].id == id) return FORMS[i].name;
    return "?";
}
static int form_by_name(const char *name) {
    for (int i = 0; name && i < FORM_COUNT; i++)
        if (!strcmp(FORMS[i].name, name)) return FORMS[i].id;
    return -1;
}
#endif
#ifdef PAP_SWITCH
#define say(fmt, a) ((void)0)   /* no message box */
#else
static void say(const char *fmt, const char *a) {
    if (!atomic_load(&g_messages) || !MT_HOST_HAS(H, notify) || !H->notify) return;
    char t[160];
    snprintf(t, sizeof t, fmt, a);
    H->notify(M, t, 2.5);
}
#endif

/* The Pokemon the combo turns the player into (on a Switch the choice cheat may not have set one yet). */
static uint16_t selected(void) {
    uint16_t f = atomic_load(&g_selected);
    return f ? f : DEFAULT_FORM;
}

/* The game's own player forms: human, Ditto, and the move forms. The game keeps their animations loaded and changes into them itself. */
static int game_form(uint16_t f) { return f == HUMAN || f == 0x1F || f == 0x46 || f == 0x99 || f == 0xCE || f == 0x128; }
static int mod_form(uint16_t f) { return f > HUMAN && f <= FORM_MAX && !game_form(f); }

/* ---------------------------------------------------------------- holds: the forms' animations (1.6)
 * A model can only be built while its form's package is loaded. The model setup (main+0x27CAD0) first destroys the character's
 * model (main+0x69D0E0), and the model build (main+0x69DBE0) then returns without building anything when the package (definition
 * +0xC6) is not loaded. The model slot keeps its pointer to the destroyed model (slot +0xC40; the count, +0xC48, is 0), and the
 * model parameter job (main+0x6A10E0, run for the four players by main+0x7187C0) reads and writes the model through it every frame
 * without checking the count. Once the deferred release has freed that model and the memory is used again, the job reads a wild
 * pointer: the Link Play crashes of 1.5 (access violation "reading address 0xffffffffffffffff" in f_71006a10e0, right after a
 * player changed into a Pokemon, before its animations were loaded).
 * Up to 1.5 every change into a Pokemon whose animations were not loaded went through that window: the form was requested first,
 * the package when the model setup asked for it, and the model was built a second time once it had loaded. With three or four
 * players each game sees every other player's changes, so it happened far more often. Since 1.6 the form's packages are
 * requested and its motion set acquired BEFORE the form is requested (as the game does for the town's Pokemon), so the model is
 * built once, at once, with its animations. The holds stay while the character is in the form, going into it, or left it less
 * than RELEASE_MS ago: the old model is only freed (deferred) after the setup that replaced it, and a talk that turns the player
 * human for a moment no longer unloads the Pokemon. char_setup checks every model setup of a player in one of this mod's forms
 * anyway: one whose animations are not loaded (the game rebuilt the model by itself) is built as the human instead.
 * A world reset (h_motion_reset) releases every package and motion set: holds taken before it (gen) are forgotten, never released. */
#define HOLDS       4
#define RELEASE_MS  3000    /* a form's holds are given back this long after the character left it */
#define LOAD_MAX_MS 15000   /* a form whose package has not loaded in this time is given up */
enum { LOAD_WAIT, LOAD_READY, LOAD_FAILED };
typedef struct {
    uint16_t form, res, pkg[2];   /* the form, its animation resource, its packages: the animations' and the model's (0: none) */
    uint8_t held[2], set, filled; /* package k requested by this mod; motion set acquired; res / pkg looked up */
    uint8_t ready, pad;           /* LOAD_READY was logged */
    uint32_t gen;                 /* g_reset_gen when taken */
    uint32_t asked, used;         /* ms clock: packages requested; the character last in or going into the form */
} Hold;
typedef struct { Hold h[HOLDS]; } Holds;
static _Atomic uint32_t g_reset_gen = 1;
static Holds g_holds;   /* the player's own: its update and model setup only */

static void hold_clear(Hold *h) { memset(h, 0, sizeof *h); }
static void hold_release(Hold *h) {   /* gives back what this mod took for the form */
    uint64_t mgr = pkg_mgr();
    if (h->gen == atomic_load(&g_reset_gen) && mgr) {
        if (h->set) game_call(FN_MSET_REL, mgr, h->res, 0);
        for (int k = 1; k >= 0; k--)
            if (h->held[k]) game_call(FN_PKG_REL, mgr, h->pkg[k], 0);
    }
    hold_clear(h);
}
/* Looks the form up (its record from the model setup, else def_record) and requests its packages. */
static void hold_fill(Hold *h, uint64_t rec, uint32_t now) {
    uint64_t mgr = pkg_mgr();
    if (!rec) rec = def_record(h->form);
    if (!rec || !mgr) return;   /* not yet: tried again at the next look */
    uint64_t d = def_data(rec);
    uint16_t res = 0, model = 0;
    r16(d + DEF_RES, &res), r16(d + DEF_MODEL_PKG, &model);
    h->res = res;
    h->pkg[0] = res ? pkg_of(mgr, res) : 0;
    h->pkg[1] = model != h->pkg[0] ? model : 0;
    for (int k = 0; k < 2; k++) {
        if ((uint16_t)(h->pkg[k] - 1) >= PKG_MAX) h->pkg[k] = 0;
        else game_call(FN_PKG_REQ, mgr, h->pkg[k], 0), h->held[k] = 1;
    }
    h->filled = 1;
    h->asked = now;
    mt_logf(H, M, MT_LOG_INFO, "loading %s (form %u): animation resource %u, packages %u / %u", form_name(h->form), h->form, res,
            h->pkg[0], h->pkg[1]);
}
/* The holds of a form: found, or taken now (packages requested). NULL when every hold is in use. rec: the form's definition record
   when the caller has it (the model setup), else 0. */
CAVE2_FN static Hold *hold_take(Holds *hs, uint16_t form, uint64_t rec, uint64_t now_full) {
    uint32_t gen = atomic_load(&g_reset_gen), now = (uint32_t)now_full;
    Hold *h = NULL, *free_one = NULL;
    for (int i = 0; i < HOLDS; i++) {
        Hold *x = &hs->h[i];
        if (x->form && x->gen != gen) hold_clear(x);   /* taken before a world reset: the reset released it */
        if (x->form == form) h = x;
        else if (!x->form && !free_one) free_one = x;
    }
    if (!h) {
        if (!free_one) return NULL;
        h = free_one;
        h->form = form, h->gen = gen, h->asked = h->used = now;
    }
    if (!h->filled) hold_fill(h, rec, now);
    h->used = now;
    return h;
}
/* LOAD_READY once the form's packages are loaded; then its motion set is acquired (that binds the animations to it).
   A form whose definition could not be looked up counts as ready: the form is requested, and the model setup, which has the
   game's own record of it, takes the holds then (building the human until they are loaded, see prepare_model). */
CAVE2_FN static int hold_ready(Hold *h, uint64_t now_full) {
    uint32_t now = (uint32_t)now_full;
    uint64_t mgr = pkg_mgr();
    if (!h->filled) {
        static _Atomic int warned;
        if (!atomic_exchange(&warned, 1))
            mt_logf(H, M, MT_LOG_WARN, "cannot look up form %u's definition: its animations load at its first model setup", h->form);
        return LOAD_READY;
    }
    if (!mgr) return LOAD_WAIT;
    for (int k = 0; k < 2; k++)
        if (h->held[k] && !(uint32_t)game_call(FN_PKG_READY, mgr, h->pkg[k], 0))
            return now - h->asked > LOAD_MAX_MS ? LOAD_FAILED : LOAD_WAIT;
    if (!h->set && h->res && motion_set_uses(motion_set(h->res)) >= 0) {
        game_call(FN_MSET_ACQ, mgr, h->res, 0);
        h->set = 1;
    }
    if (!h->ready) {
        h->ready = 1;
        mt_logf(H, M, MT_LOG_INFO, "%s (form %u) loaded in %u ms", form_name(h->form), h->form, now - h->asked);
    }
    return LOAD_READY;
}
/* Gives back the holds of forms the character left RELEASE_MS ago; a, b, c: the forms it is in or going into. */
static void holds_tick(Holds *hs, uint16_t a, uint16_t b, uint16_t c, uint64_t now_full) {
    uint32_t gen = atomic_load(&g_reset_gen), now = (uint32_t)now_full;
    for (int i = 0; i < HOLDS; i++) {
        Hold *h = &hs->h[i];
        if (!h->form) continue;
        if (h->gen != gen) hold_clear(h);
        else if (h->form == a || h->form == b || h->form == c) h->used = now;
        else if (now - h->used >= RELEASE_MS) {
            mt_logf(H, M, MT_LOG_DEBUG, "releasing %s (form %u)", form_name(h->form), h->form);
            hold_release(h);
        }
    }
}
/* The model setup of a player in one of this mod's forms (h_char_setup: x0 = the form's definition record, w8 = its animation
   resource, x25 + 0xE94 = where the game stores w8 next). Returns 0 when the form's animations are ready: the game builds the model
   with them. Otherwise 1: the human is built instead (its record, resource and current form), so the slot is never left without a
   model; the mod asks for the form again once it has loaded. */
static int prepare_model(MtHookCtx *c, Holds *hs, uint64_t ch, uint16_t form) {
    uint64_t now = now_ms(), rec = H->reg_get(c, 0);
    Hold *h = hold_take(hs, form, rec, now);
    if (h && hold_ready(h, now) == LOAD_READY) return 0;
    uint64_t human = def_record(HUMAN);
    uint16_t res = HUMAN_RES;
    if (human) {
        r16(def_data(human) + DEF_RES, &res);
        H->reg_set(c, 0, human);
    }
    H->reg_set(c, 8, res);
    w16(H->reg_get(c, 25) + 0xE94, res);
    w16(ch + P_FORM_NOW, HUMAN);   /* vfunc 0x1D0, which the rest of the setup asks */
    w8(ch + P_ISDITTO, 0);
    return 1;
}

static void request(uint64_t P, uint16_t state) {
    w16(P + P_FORM_WANT, state);
    w16(P + P_REQ_STATE, state);
    w16(P + P_REQ_ANIM, TRANSFORM_ANIM);
    w8(P + P_REQ_GO, 1);
    g_last_request = now_ms();
    g_settled_since = 0;
}
/* Asks for a form on the player once its animations are loaded (at once for the game's own forms, and when they are loaded). */
static void request_form(uint64_t P, uint16_t form) {
    if (mod_form(form)) {
        uint64_t now = now_ms();
        Hold *h = hold_take(&g_holds, form, 0, now);
        if (!h || hold_ready(h, now) != LOAD_READY) {
            if (g_load != form) g_load_since = now;
            g_load = form;
            return;
        }
    }
    g_load = 0;
    request(P, form);
}
static void transform(uint64_t P, uint16_t form) {
    atomic_store(&g_form, form);
    g_wrong_since = g_revert_window = 0, g_reverts = 0;
    atomic_store(&g_interaction_at, 0);
    uint16_t id = 0;
    r16(P + 0x27FE, &id);
    mt_logf(H, M, MT_LOG_INFO, "transform: player id 0x%x into %s (form %u)", id, form_name(form), form);
    say("Play as Pokemon: %s", form_name(form));
    request_form(P, form);
}
static void turn_back(uint64_t P) {
    uint16_t cur = 0;
    atomic_store(&g_form, 0);
    g_load = 0;
    if (!r16(P + P_FORM_NOW, &cur) || cur != HUMAN) request(P, HUMAN);
    g_hop_until = 0;
    g_takeoff = g_descending = 0;
    g_wrong_since = 0;
    atomic_store(&g_interaction_at, 0);
}
/* The player's update: the form waiting for its animations is requested once they are loaded. */
static void load_tick(uint64_t P) {
    uint16_t form = g_load, cur = 0;
    if (!form) return;
    if (atomic_load(&g_form) != form) {   /* turned back, or another form chosen meanwhile */
        g_load = 0;
        return;
    }
    uint64_t now = now_ms();
    uint8_t go = 1;
    Hold *h = hold_take(&g_holds, form, 0, now);
    int st = h ? hold_ready(h, now) : now - g_load_since > LOAD_MAX_MS ? LOAD_FAILED : LOAD_WAIT;
    if (st == LOAD_WAIT) return;
    if (st == LOAD_READY) {   /* one form change at a time, as ever */
        if (now - g_last_request < REQUEST_GAP_MS || !rd(P + P_REQ_GO, &go, 1) || go) return;
        g_load = 0;
        request(P, form);
        return;
    }
    g_load = 0;
    mt_logf(H, M, MT_LOG_WARN, "%s (form %u): its animations did not load, staying as you are", form_name(form), form);
    say("Play as Pokemon: %s could not be loaded", form_name(form));
    atomic_store(&g_form, 0);
    if (r16(P + P_FORM_NOW, &cur) && cur != HUMAN) request(P, HUMAN);
}

/* A form change rebuilds the player's model over several frames, partly on the game's worker threads. Requests are queued:
   the newest one waits until the last change is complete (and its animations loaded) and has been for a moment. (The crash when
   switching fast in 1.1.0 was most likely the empty model slot described under "holds", hit more often by fast changes.) */
static void want(int form, uint64_t delay) {
    g_want = form;
    g_want_after = now_ms() + delay;
}
static int settled(uint64_t P, uint64_t now) {
    uint64_t since = now - g_last_request;
    if (!g_last_request) return 1;
    if (since < REQUEST_GAP_MS) return 0;
    if (since > REQUEST_MAX_MS) return 1;
    uint16_t cur = 0, form = atomic_load(&g_form);
    uint8_t go = 1;
    if (!r16(P + P_FORM_NOW, &cur) || !rd(P + P_REQ_GO, &go, 1) || go || cur != (form ? form : HUMAN) || g_load) {
        g_settled_since = 0;
        return 0;
    }
    if (!g_settled_since) g_settled_since = now;
    return now - g_settled_since >= SETTLED_MS;
}
static void apply_wanted(uint64_t P) {
    if (g_want < 0) return;
    uint64_t now = now_ms();
    if (now < g_want_after || !settled(P, now)) return;
    int form = g_want;
    g_want = -1;
    if (form == atomic_load(&g_form)) return;
    if (form) transform(P, (uint16_t)form);
    else turn_back(P);
}

/* ---------------------------------------------------------------- settings */
#ifdef PAP_SWITCH
/* No settings on a Switch: everything on, each Pokemon's own ability, Normal flying speed. The Pokemon comes from the cheat. */
static void read_settings(void) {}
#else
static void read_settings(void) {
    const char *list = H->config_string(M, "list");
    const char *key = list && !strcmp(list, LIST_M_Z) ? "pokemon_m_z" : list && !strcmp(list, LIST_EXPERIMENTAL) ? "experimental" : "pokemon_a_l";
    int id = form_by_name(H->config_string(M, key));
    atomic_store(&g_selected, (uint16_t)(id > 0 ? id : DEFAULT_FORM));
    atomic_store(&g_fly, H->config_bool(M, "fly"));
    const char *speed = H->config_string(M, "fly_speed");
    atomic_store(&g_fly_top, speed && !strcmp(speed, "Slow") ? 250 : speed && !strcmp(speed, "Fast") ? 600 : 400);
    atomic_store(&g_cycle, H->config_bool(M, "cycle"));
    atomic_store(&g_messages, H->config_bool(M, "messages"));
    atomic_store(&g_abilities, H->config_bool(M, "abilities"));
    atomic_store(&g_interact, H->config_bool(M, "interact"));
    const char *ab = H->config_string(M, "ability");
    int kind = -1;
    for (int i = 0; ab && i < AB_KINDS; i++)
        if (!strcmp(ab, AB_NAMES[i])) kind = i;
    atomic_store(&g_ability, kind);
}
static void on_config(MtMod *mod, const char *key, void *user) {
    (void)mod, (void)key, (void)user;
    read_settings();
    atomic_store(&g_settings_changed, 1);   /* the player's next update applies it (game thread) */
}
#endif

/* ZL + D-pad Right / Left: the next / previous Pokemon in the A-Z list (experimental forms are left out). */
static void cycle(int dir) {
    uint16_t cur = selected();
    int at = -1;
    for (int i = 0; i < POKEMON_COUNT; i++)
        if (FORMS[i].id == cur) at = i;
    at = at < 0 ? 0 : (at + dir + POKEMON_COUNT) % POKEMON_COUNT;
    uint16_t form = FORMS[at].id;
    atomic_store(&g_selected, form);
    if (atomic_load(&g_form) || g_want > 0) {   /* transformed: turn into it once the player stops flicking through */
        want(form, CYCLE_PAUSE_MS);
        say("Play as Pokemon: %s", FORMS[at].name);
    } else say("Play as Pokemon: %s (ZL + L3 to transform)", FORMS[at].name);
}

static int key_down(const char *setting) {
    if (!MT_HOST_HAS(H, key_down) || !H->key_down) return 0;
    const char *k = H->config_string(M, setting);
    return k && *k && H->key_down(M, k);
}

/* A combo fires once when it becomes held (ZL and the button, in either order). */
static int combo(uint32_t now, uint32_t before, uint32_t dir) {
    uint32_t m = MT_PAD_ZL | dir;
    return (now & m) == m && (before & m) != m;
}

/* Which of the player's input the game does not get (pad_block), told to the host only when it changes. */
static void block(uint32_t buttons, int sticks) {
    static uint32_t cur_buttons;
    static int cur_sticks;
    if (buttons == cur_buttons && sticks == cur_sticks) return;
    cur_buttons = buttons, cur_sticks = sticks;
    if (!MT_HOST_HAS(H, pad_block) || !H->pad_block) return;
    MtPad m;
    memset(&m, 0, sizeof m);
    m.buttons = buttons;
    if (sticks) m.lx = m.ly = m.rx = m.ry = 1;
    H->pad_block(M, 0, buttons || sticks ? &m : NULL);
}

#ifdef PAP_SWITCH
/* No message box on a Switch, so no list: the cheat and ZL + D-pad Left / Right pick the Pokemon. */
static int g_menu, g_prev_key_menu;
static void menu_open(void) {}
static void menu_tick(const MtPad *pad, uint32_t was, int key_menu) { (void)pad, (void)was, (void)key_menu; }
#else
/* ---------------------------------------------------------------- the menu
 * Modtopia has no drawing for mods, so the menu is its message box: a list of a few lines around the cursor, shown again
 * whenever it changes. While it is open the game gets no input from the player. The entries are FORMS (the Pokemon A to Z,
 * then the experimental forms); turning back is ZL + L3, so the player's own character is not one of them (1.7.1). It opens
 * on the Pokemon picked last (the one you are, or the one ZL + L3 turns you into). */
#define MENU_LINES 9
#define MENU_ENTRIES FORM_COUNT
enum { NAV_UP = 1, NAV_DOWN = 2, NAV_LEFT = 4, NAV_RIGHT = 8, NAV_OK = 16, NAV_BACK = 32, NAV_PREV = 64, NAV_NEXT = 128 };
static int g_menu;   /* 0 closed, 1 open, 2 closed but waiting for the buttons to be let go */
static int g_menu_at, g_prev_key_menu;
static uint32_t g_nav_was;
static uint64_t g_nav_repeat, g_menu_shown;

static const char *menu_name(int i) { return FORMS[i].name; }
static int any_key(const char *a, const char *b) {
    if (!MT_HOST_HAS(H, key_down) || !H->key_down) return 0;
    return H->key_down(M, a) || (b && H->key_down(M, b));
}
static void menu_show(void) {
    char t[640];
    int n = snprintf(t, sizeof t, "Play as Pokemon  (%d / %d)\n", g_menu_at + 1, MENU_ENTRIES);
    int first = g_menu_at - MENU_LINES / 2;
    if (first > MENU_ENTRIES - MENU_LINES) first = MENU_ENTRIES - MENU_LINES;
    if (first < 0) first = 0;
    for (int i = first; i < first + MENU_LINES && i < MENU_ENTRIES && n < (int)sizeof t; i++)
        n += snprintf(t + n, sizeof t - (size_t)n, i == g_menu_at ? ">  %s  <\n" : "    %s\n", menu_name(i));
    if (n < (int)sizeof t)
        snprintf(t + n, sizeof t - (size_t)n, "Up/Down: move   Left/Right: 10   L/R: letter   A/Enter: choose   B/Esc: close");
    if (MT_HOST_HAS(H, notify) && H->notify) H->notify(M, t, 2.0);
    g_menu_shown = now_ms();
}
static void menu_open(void) {
    uint16_t cur = atomic_load(&g_form) ? atomic_load(&g_form) : selected();
    g_menu_at = 0;
    for (int i = 0; i < FORM_COUNT; i++)
        if (FORMS[i].id == cur) g_menu_at = i;
    g_menu = 1;
    g_nav_was = ~0u;   /* what is held now does not count as a press */
    block(0xFFFF, 1);
    menu_show();
}
static void menu_close(const char *text) {
    g_menu = 2;
    if (MT_HOST_HAS(H, notify) && H->notify) H->notify(M, text, 1.5);
}
/* The first entry whose name starts with another letter than the cursor's, forwards or backwards (Pokemon only). */
static int menu_letter(int dir) {
    int i = g_menu_at;
    if (i >= POKEMON_COUNT) return dir > 0 ? 0 : POKEMON_COUNT - 1;   /* from the experimental forms: back into the Pokemon */
    char c = FORMS[i].name[0];
    while (i >= 0 && i < POKEMON_COUNT && FORMS[i].name[0] == c) i += dir;
    if (i < 0) return FORM_COUNT - 1;   /* off the start: to the end, as Up does */
    if (i >= POKEMON_COUNT) return i < FORM_COUNT ? i : 0;
    if (dir < 0)   /* backwards: to the first name of that letter */
        while (i > 0 && FORMS[i - 1].name[0] == FORMS[i].name[0]) i--;
    return i;
}
static void menu_tick(const MtPad *pad, uint32_t was, int key_menu) {
    uint32_t b = pad->buttons, nav = 0;
    uint64_t now = now_ms();
    (void)was;
    if (g_menu == 2) {   /* closed: give the game its input back once nothing is held (or A / B would act in the game) */
        if (!b && !any_key("Return", "Escape")) {
            g_menu = 0;
            block(0, 0);
        }
        return;
    }
    if ((b & MT_PAD_UP) || pad->ly > 20000 || any_key("Up", NULL)) nav |= NAV_UP;
    if ((b & MT_PAD_DOWN) || pad->ly < -20000 || any_key("Down", NULL)) nav |= NAV_DOWN;
    if ((b & MT_PAD_LEFT) || any_key("Left", "PageUp")) nav |= NAV_LEFT;
    if ((b & MT_PAD_RIGHT) || any_key("Right", "PageDown")) nav |= NAV_RIGHT;
    if ((b & MT_PAD_A) || any_key("Return", "Keypad Enter")) nav |= NAV_OK;
    if ((b & MT_PAD_B) || any_key("Escape", "Backspace") || key_menu) nav |= NAV_BACK;
    if (b & MT_PAD_L) nav |= NAV_PREV;
    if (b & MT_PAD_R) nav |= NAV_NEXT;
    uint32_t pressed = nav & ~g_nav_was, moves = NAV_UP | NAV_DOWN | NAV_LEFT | NAV_RIGHT;
    if (g_nav_was == ~0u) pressed = 0;
    if (pressed & moves) g_nav_repeat = now + 350;
    else if ((nav & moves) && (nav & moves) == (g_nav_was & moves) && now >= g_nav_repeat) {   /* held: repeat */
        pressed |= nav & moves;
        g_nav_repeat = now + 70;
    }
    g_nav_was = nav;

    if (pressed & NAV_BACK) {
        menu_close("Play as Pokemon: closed");
        return;
    }
    if (pressed & NAV_OK) {
        atomic_store(&g_selected, FORMS[g_menu_at].id);
        want(FORMS[g_menu_at].id, 0);
        menu_close(menu_name(g_menu_at));
        return;
    }
    int at = g_menu_at;
    if (pressed & NAV_UP) at--;
    if (pressed & NAV_DOWN) at++;
    if (pressed & NAV_LEFT) at = at == 0 ? -1 : at < 10 ? 0 : at - 10;
    if (pressed & NAV_RIGHT) at = at == MENU_ENTRIES - 1 ? MENU_ENTRIES : at + 10 > MENU_ENTRIES - 1 ? MENU_ENTRIES - 1 : at + 10;
    if (pressed & NAV_PREV) at = menu_letter(-1);
    if (pressed & NAV_NEXT) at = menu_letter(1);
    at = (at + MENU_ENTRIES) % MENU_ENTRIES;   /* off one end: to the other */
    if (at != g_menu_at) {
        g_menu_at = at;
        menu_show();
    } else if (now - g_menu_shown >= 1000) menu_show();   /* keep the message up */
}

#endif

/* Something in hand to place (a block, furniture): the game raises and lowers it with ZL + D-pad Up / Down, so ZL + D-pad Down
   is not the ability then. Found live 2026-11-23 (memory diffs, hands empty vs a block): P+0x53A8 is 2 in the item-in-hand
   mode (also in the moment between two items or after placing), u16 P+0x2AD8 the item held (0xFFFF none), P+0x36A0 the
   placement preview (flickers to 0 while the item changes). Any of them counts. */
#define P_HAND_MODE   0x53A8   /* u32: 2 = item in hand */
#define P_HAND_ITEM   0x2AD8   /* u16: item id, 0xFFFF = none */
#define P_PREVIEW     0x36A0   /* u8: placement preview shown */
static int item_in_hand(uint64_t P) {
    uint32_t mode = 0;
    uint16_t item = 0xFFFF;
    uint8_t preview = 0;
    if (!P) return 0;
    rd(P + P_HAND_MODE, &mode, 4), r16(P + P_HAND_ITEM, &item), rd(P + P_PREVIEW, &preview, 1);
    return mode == 2 || item != 0xFFFF || preview;
}

static void buttons(uint64_t P) {
    MtPad pad;
    memset(&pad, 0, sizeof pad);
    if (MT_HOST_HAS(H, pad_read) && H->pad_read) H->pad_read(M, 0, &pad);
    uint32_t b = pad.buttons, was = g_prev_buttons;
    g_prev_buttons = b;
    g_lx = pad.lx, g_ly = pad.ly;
    int kon = key_down("key_transform"), koff = key_down("key_turn_back");
    int key_on = kon && !g_prev_key_on, key_off = koff && !g_prev_key_off;
    g_prev_key_on = kon, g_prev_key_off = koff;

    int kmenu = key_down("key_menu"), key_menu = kmenu && !g_prev_key_menu;
    g_prev_key_menu = kmenu;
    int kab = key_down("key_ability"), key_ability = kab && !g_prev_key_ability;
    g_prev_key_ability = kab;
    g_ab_press = PRESS_NONE;

    if (g_menu) {
        menu_tick(&pad, was, key_menu);
        apply_wanted(P);
        return;
    }
    /* The stick clicks belong to the combos while ZL is held: the game does not see them then. While transformed with
       interacting on, ZR is this mod's alone (flying, the ability): with isDitto 0 the game would start its human ZR action. */
    uint32_t hide = (b & MT_PAD_ZL) ? MT_PAD_LSTICK | MT_PAD_RSTICK : 0;
    if (atomic_load(&g_interact) && atomic_load(&g_form) && (atomic_load(&g_abilities) || atomic_load(&g_fly))) hide |= MT_PAD_ZR;
    block(hide, 0);
    int transformed = atomic_load(&g_form) || g_want > 0;
    if (key_menu || combo(b, was, MT_PAD_RSTICK)) menu_open();
    else if (combo(b, was, MT_PAD_LSTICK)) want(transformed ? 0 : selected(), 0);   /* ZL + L3: there and back */
    else if (key_on) want(selected(), 0);
    else if (key_off) want(0, 0);
    else if (atomic_load(&g_cycle) && combo(b, was, MT_PAD_RIGHT)) cycle(1);
    else if (atomic_load(&g_cycle) && combo(b, was, MT_PAD_LEFT)) cycle(-1);
    else if (atomic_exchange(&g_settings_changed, 0) && atomic_load(&g_form) && atomic_load(&g_selected) != atomic_load(&g_form))
        want(atomic_load(&g_selected), 0);   /* a new Pokemon picked in the settings while transformed */
    /* The ability: ZL + D-pad Down (not with an item in hand: the game lowers it then), ZR alone (abilities() leaves it to
       flying Pokemon), or its keyboard key */
    if (combo(b, was, MT_PAD_DOWN)) g_ab_press = item_in_hand(P) ? PRESS_NONE : PRESS_COMBO;
    else if ((b & MT_PAD_ZR) && !(was & MT_PAD_ZR) && !(b & MT_PAD_ZL)) g_ab_press = PRESS_ZR;
    else if (key_ability) g_ab_press = PRESS_KEY;
    apply_wanted(P);
}

/* Some of the game's form changes skip RequestState. Talking to most Pokemon turns the player human through h_to_human's
   function (the ones that comment on the transformation don't): the player stays human until the game stopped asking for
   INTERACTION_QUIET_MS and the player walks off, then turns back into the Pokemon. Any other time, a form other than the chosen
   one that stays for REVERT_WAIT_MS with no request under way is undone, as ZL + L3 would. If the game keeps doing it (more than REVERT_LIMIT times in REVERT_WINDOW_MS),
   the player is left as the game wants and counts as turned back: ZL + L3 transforms again. */
static void keep_form(uint64_t P) {
    uint16_t form = atomic_load(&g_form), cur = 0;
    uint8_t go = 1;
    uint32_t perms = 0;
    uint64_t now = now_ms(), gm = r64(MAIN + GAME_MGR), ia = atomic_load(&g_interaction_at);
    if (!ia) g_interaction_start = 0;
    if (form && ia) {   /* an interaction (talking) turned the player human: back once it is over and the player walks off */
        if (!g_interaction_start) g_interaction_start = ia;
        g_wrong_since = 0;
        int walking = g_lx > WALK_STICK || g_lx < -WALK_STICK || g_ly > WALK_STICK || g_ly < -WALK_STICK;
        if (now - ia < INTERACTION_QUIET_MS || g_menu || !walking) {
            g_walk_since = 0;
            return;
        }
        if (!g_walk_since) g_walk_since = now;
        if (now - g_walk_since < WALK_MS) return;
        atomic_store(&g_interaction_at, 0);
        mt_logf(H, M, MT_LOG_INFO, "the interaction is over (%llu ms): back into %s", (unsigned long long)(ia - g_interaction_start), form_name(form));
        g_interaction_start = g_walk_since = 0;
        if (g_want < 0 && !g_load && r16(P + P_FORM_NOW, &cur) && cur != form && rd(P + P_REQ_GO, &go, 1) && !go) request_form(P, form);
        return;
    }
    if (!form || g_want >= 0 || g_load || !gm || !rd(gm + GM_PERMISSIONS, &perms, 4) || !perms || !r16(P + P_FORM_NOW, &cur)
        || !rd(P + P_REQ_GO, &go, 1) || go || cur == form || now - g_last_request < REQUEST_GAP_MS) {
        g_wrong_since = 0;
        return;
    }
    if (!g_wrong_since) g_wrong_since = now;
    if (now - g_wrong_since < REVERT_WAIT_MS) return;
    g_wrong_since = 0;
    if (!g_revert_window || now - g_revert_window > REVERT_WINDOW_MS) g_revert_window = now, g_reverts = 0;
    if (++g_reverts > REVERT_LIMIT) {
        mt_logf(H, M, MT_LOG_INFO, "the game keeps turning the player into form %u: leaving it", cur);
        atomic_store(&g_form, 0);
        g_hop_until = 0;
        g_takeoff = g_descending = 0;
        say("Play as Pokemon: the game turned you back (%s to transform again)", "ZL + L3");
        return;
    }
    mt_logf(H, M, MT_LOG_INFO, "the game turned the player into form %u: back into %s (form %u)", cur, form_name(form), form);
    request_form(P, form);
}

/* ---------------------------------------------------------------- interacting (1.7)
 * Setting a form sets the player's isDitto byte (P+0x378D, FUN_71002f2058) to 1 for every form but the human: the game then treats
 * the player as its Ditto blob and skips the human's things, so a transformed player could not open doors, use the crafting bench,
 * open the bag or build (placement preview main+0x3DD63C, held item 0x277BF4 / 0x278598, menu check 0x259EE4, event queue
 * 0x45D5A0 and more). Tested live (2026-11-21): with it at 0 all of these work for a Pokemon, and so do the abilities, but ZR then
 * also starts the human's ZR action (ACT_HUMAN_ZR), which buttons() hides from the game. The game writes the byte only when the form
 * changes, so once the mod's form is in place and settled this sets it to 0 (back to 1 when the setting is turned off). */
static void interact_tick(uint64_t P) {
    uint16_t form = atomic_load(&g_form), cur = 0, pend = 0;
    uint8_t go = 1, ditto = 0, target = atomic_load(&g_interact) ? 0 : 1;
    static uint16_t told;
    if (!form || g_load || !r16(P + P_FORM_NOW, &cur) || cur != form || !mod_form(cur)) return;
    if (!rd(P + P_REQ_GO, &go, 1) || go || !r16(P + P_REQ_STATE, &pend) || pend || now_ms() - g_last_request < REQUEST_GAP_MS) return;
    if (!rd(P + P_ISDITTO, &ditto, 1) || ditto == target) return;
    w8(P + P_ISDITTO, target);
    if (told != cur || target) {
        told = target ? 0 : cur;
        mt_logf(H, M, MT_LOG_INFO, "interacting: %s (form %u) %s", form_name(cur), cur, target ? "back to the game's Pokemon rules (setting off)" : "can use doors, the bench, the bag and build");
    }
}

/* Seats. What a player is busy with is [main+0x35650E8] + 0x140 + 4 * slot (-1 none). Sitting while transformed set it to 15 and
   it stayed: the seat waits for a sit motion a Pokemon does not have, and menus, moves, prompts and walking stayed locked, even as
   the human, until the save was reloaded (found live 2026-11-21). Using a placed object goes through FUN_710074FB80 (kind,
   start/stop, cell, player slot), which sets that: a chair is kind 6 (15), a bed kind 7 (16), a box kind 8 (17), the crafting bench
   kind 9 (18), and doors do not go through it (logged live 2026-11-22). A chair's FUN_71007C1838 (x0 the object, w3 bit 0 = only
   asking whether it can be used) and a bed's FUN_710079D948 (the same in w2) start the sit / lie-down motion (FUN_7100722B30 /
   0x7232C0) before they get there, so for the transformed player both answer "no" at their entry, before they change anything:
   pressing A at a chair or bed does nothing (the prompt still shows). The acting player is [[PLAYER_GLOBAL] + 0x30], or + 0x38
   when the object's bit 13 of +10 is set and [main+0x3561880] + 0x232 is set (FUN_71000207d4), as both functions pick it.
   Confirmed in game 2026-11-22. */
CAVE2_FN static int no_seat(MtHookCtx *c, int ask_reg, const char *what) {
    uint64_t obj = H->reg_get(c, 0), g = r64(MAIN + PLAYER_GLOBAL), P = player(), net = r64(MAIN + 0x3561880ull);
    uint16_t flags = 0, cur = 0;
    uint8_t second = 0;
    static uint64_t told;
    if (!P || !g || !rd(obj + 10, &flags, 2)) return MT_CONTINUE;
    if (((flags >> 13) & 1) && net) rd(net + 0x232, &second, 1);
    if (r64(g + (second ? 0x38 : 0x30)) != P || !r16(P + P_FORM_NOW, &cur) || !mod_form(cur)) return MT_CONTINUE;
    if (told != obj && !(H->reg_get(c, ask_reg) & 1)) {
        told = obj;
        mt_logf(H, M, MT_LOG_INFO, "no %s for %s (form %u): a Pokemon would be stuck there", what, form_name(cur), cur);
    }
    H->reg_set(c, 0, 0);
    return MT_HANDLED;
}
/* Hand attachments. The player's attachment manager is P+0xFB0 (14 slots of 0x50 from +0x10, each with a fixed kind at +0x18:
   1, 3, 4, 2, 7, 74, 90; +0x5BA on). FUN_71002A5D5C (x0 the manager, w1 model id, ..., w5 kind, x6 placement or 0) puts a model
   on the human's hand, FUN_71002A5150 (manager, kind) takes it off. Picking an item up attaches it as kind 7, slot 4 (found live
   2026-11-22 with hardware write watchpoints, re/live/watchw.py: P+0x1100 = the slot's model, P+0x110C = 0x3E9, the manager's
   +0x556 = P+0x1506 set to 1). A Pokemon has no such hand: the item stayed at its feet until the bag or a form change took it
   off. A Pokemon holds nothing, so for a transformed player nothing is attached (confirmed in game 2026-11-22). */
#define P_ATTACH 0xFB0ull
static int h_attach(MtHookCtx *c, void *u) {
    (void)u;
    uint64_t P = player();
    uint16_t cur = 0;
    uint32_t kind = (uint32_t)H->reg_get(c, 5) & 0xFF;
    static uint32_t told;
    if (!P || H->reg_get(c, 0) != P + P_ATTACH || !r16(P + P_FORM_NOW, &cur) || !mod_form(cur)) return MT_CONTINUE;
    if (kind < 32 && !(told >> kind & 1)) {
        told |= 1u << kind;
        mt_logf(H, M, MT_LOG_INFO, "nothing in hand for %s (form %u): attachment kind %u, model %u", form_name(cur), cur, kind,
                (unsigned)(H->reg_get(c, 1) & 0xFFFF));
    }
    return MT_HANDLED;
}
static int h_chair_use(MtHookCtx *c, void *u) { (void)u; return no_seat(c, 3, "sitting"); }
static int h_bed_use(MtHookCtx *c, void *u) { (void)u; return no_seat(c, 2, "lying down"); }

static void remote_model(MtHookCtx *c, uint64_t ch, uint16_t res);   /* Link Play, below */

static int h_char_setup(MtHookCtx *c, void *u) {   /* strh w8, [x25, #0xe94]: w8 = resource ID, x19 = character */
    (void)u;
    uint64_t P = player();
    if (!P || H->reg_get(c, 19) != P) {
        if (P) remote_model(c, H->reg_get(c, 19), (uint16_t)H->reg_get(c, 8));
        return MT_CONTINUE;
    }
    /* The model being built is of the current form (vfunc 0x1D0). The human and the game's own forms are the game's business:
       their animations are always loaded, and the mod never takes or gives back a hold on them (before 1.5 it did, and after a
       world reset that release took the game's own hold on the human animations away). One of this mod's forms is built only
       with its animations loaded (prepare_model): the mod's own requests always wait for that, so this only acts when the game
       rebuilt the model by itself. */
    uint16_t res = (uint16_t)H->reg_get(c, 8), form = atomic_load(&g_form), cur = 0;
    r16(P + P_FORM_NOW, &cur);
    w16(H->reg_get(c, 25) + 0xE94, res);   /* the store this hook point replaces, first (the game repeats it) */
    if (!mod_form(cur)) return MT_CONTINUE;
    mt_logf(H, M, MT_LOG_DEBUG, "the player's model: animation resource %u (form %u)", res, cur);
    if (prepare_model(c, &g_holds, P, cur)) {
        mt_logf(H, M, MT_LOG_INFO, "the game builds the player as %s (form %u) before its animations are loaded: as the human until they are",
                form_name(cur), cur);
        if (form == cur && g_load != cur) g_load = cur, g_load_since = now_ms();
        g_last_request = now_ms();   /* the next form change no sooner than REQUEST_GAP_MS after this one */
        g_settled_since = 0;
    }
    return MT_CONTINUE;
}

/* ---------------------------------------------------------------- flying (v0.7, controls 1.5)
 * Species whose motion 7 is a flying motion (info byte 0x22) can fly: ZR on foot starts the native hover (no gravity),
 * ZR while flying rises, ZL descends and lands once the height stops changing, ZL + ZR drops. A held D-pad direction or stick click
 * belongs to the combos.
 *
 * 1.5: climbing and descending speed up and slow down like a ship instead of jumping straight to one speed: a press starts at
 * FLY_START of the top speed (setting fly_speed), holding speeds up to the top in FLY_RAMP_S, letting go slows to a hover in
 * FLY_BRAKE_S, and the other trigger first slows down. So a tap moves a little and holding goes far. All of it is in centimetres
 * per second of real time: up to 1.4 the mod wrote one fixed vertical speed (7) every frame, and the game's step changes with the
 * frame rate in Recompia (each frame counts as 1/60 s at 60 fps or less, shorter above), so how far a press took you depended on the
 * frame rate. How far one unit of the game's vertical speed (E_VY) moves the player in a second is measured in flight (g_fly_unit),
 * so the speeds hold whether the game scales it by its step or not. */
#define FLY_START   0.30f   /* a press starts at this part of the top speed */
#define FLY_RAMP_S  0.50f   /* holding: from there to the top speed in this many seconds */
#define FLY_BRAKE_S 0.25f   /* letting go: from the top speed to a hover in this many seconds */
#define FLY_HOP_CMS 240.0f  /* the landing hop */
#define FLY_UNIT_MIN 15.0f  /* the measured unit is kept within these (cm/s): beyond them a measurement is a bump or a block */
#define FLY_UNIT_MAX 400.0f
static float g_fly_vy;               /* the climbing speed the mod flies at (cm/s, + up) */
static float g_fly_unit = 60.0f;     /* cm/s one unit of E_VY moves the player (60: the game's step is 1/60 s per frame) */
static float g_fly_wrote, g_fly_y;   /* the speed written last frame (0: none) and the height then */
static uint64_t g_fly_us;
static int g_fly_samples;
static float g_fly_logged;

static float approach(float v, float to, float step) {
    if (v < to) return v + step > to ? to : v + step;
    return v - step < to ? to : v - step;
}
/* The climbing speed for this frame, from the triggers (target: +1 up, -1 down, 0 hover), dt seconds after the last one. */
static void fly_speed(int target, float dt) {
    float top = (float)atomic_load(&g_fly_top), start = top * FLY_START, accel = (top - start) / FLY_RAMP_S, brake = top / FLY_BRAKE_S;
    if (target > 0 && g_fly_vy >= 0) g_fly_vy = g_fly_vy < start ? start : approach(g_fly_vy, top, accel * dt);
    else if (target < 0 && g_fly_vy <= 0) g_fly_vy = g_fly_vy > -start ? -start : approach(g_fly_vy, -top, accel * dt);
    else g_fly_vy = approach(g_fly_vy, 0.0f, brake * dt);   /* let go, or the other trigger: slow down first */
}
/* The last frame wrote a speed: how far the player moved since tells what one unit of E_VY is worth. */
static void fly_measure(float wrote, float dy, float dt) {
    if (wrote > -0.3f && wrote < 0.3f) return;
    float unit = dy / dt / wrote;
    if (unit < FLY_UNIT_MIN || unit > FLY_UNIT_MAX) return;   /* blocked (a ceiling, the ground) or pushed */
    g_fly_unit += 0.15f * (unit - g_fly_unit);
    g_fly_samples++;
    float change = g_fly_unit / (g_fly_logged > 0 ? g_fly_logged : 1.0f);
    if (g_fly_samples >= 30 && (g_fly_logged == 0 || change > 1.25f || change < 0.8f)) {
        g_fly_logged = g_fly_unit;
        mt_logf(H, M, MT_LOG_INFO, "flying: one unit of vertical speed moves %.0f cm a second (frames of %.1f ms)", g_fly_unit, dt * 1000.0f);
    }
}
static void fly(uint64_t P) {
    (void)P;
    /* The emulator version saw the buttons about 12 times a second; here they are read every frame, so a few frames of
       both triggers down while changing direction, or of ZR alone while letting go after a drop, must not count as a drop
       or a take-off: a drop needs both held for DROP_HOLD_MS, and after a drop or a landing only a new press of ZR
       takes off. */
    uint64_t now = now_ms(), us = now_us();
    uint32_t b = g_prev_buttons;
    int zr = (b & MT_PAD_ZR) != 0, zl = (b & MT_PAD_ZL) != 0, zr_pressed = zr && !g_zr_was, descending = 0;
    uint64_t t, E, set, recs, hover, info, cur, ci, idle;
    uint32_t count = 0;
    uint8_t kind = 0, motion = 0;
    float y = 0, d, dt = g_fly_us && us > g_fly_us ? (float)(us - g_fly_us) / 1e6f : 0.0f, wrote = g_fly_wrote, last_y = g_fly_y;
    int timed = dt >= 0.002f && dt <= 0.05f;   /* a normal frame, not the first one or one after a pause */
    if (dt < 0.001f) dt = 0.001f;
    if (dt > 0.05f) dt = 0.05f;
    g_fly_us = us, g_fly_wrote = 0;
    g_zr_was = zr;
    if (!zr) g_takeoff = 0;
    else if (zr_pressed && !zl) g_takeoff = 1;
    if (!(zr && zl)) g_both_since = 0;

    t = r64(MAIN + ENTITY_TABLE), E = t ? r64(t + 0x58) : 0;
    set = E ? r64(E + E_MSET) : 0;
    if (!set || !rd(set + 0xD0, &count, 4) || count < MOTION_HOVER + 1) goto still;
    recs = r64(set + 0xC8), hover = recs ? r64(recs + 8 * MOTION_HOVER) : 0, info = hover ? r64(hover + 8) : 0;
    if (!info || !rd(info, &kind, 1) || kind != INFO_FLYING) goto still;   /* this species cannot fly */
    rd(E + E_Y, &y, 4);
    g_fly_y = y;
    if (g_hop_until) {   /* the landing hop: a moment up so the game plays its own fall and landing */
        if (now < g_hop_until) {
            wf(E + E_VY, FLY_HOP_CMS / g_fly_unit);
            goto still;
        }
        g_hop_until = 0;
    }
    if (b & (MT_PAD_LEFT | MT_PAD_UP | MT_PAD_RIGHT | MT_PAD_DOWN | MT_PAD_LSTICK | MT_PAD_RSTICK)) {
        g_both_since = 0;
        goto still;
    }
    cur = r64(E + E_MOTION), ci = cur ? r64(cur + 8) : 0, idle = r64(recs + 8 * MOTION_IDLE);
    if (!ci || !rd(ci, &motion, 1)) goto still;
    if (motion != INFO_FLYING) {   /* on foot or falling: ZR pressed (not just still held) takes off */
        if (g_takeoff && !zl) w64(E + E_MOTION, hover);
        goto still;
    }
    if (timed) fly_measure(wrote, y - last_y, dt);
    if (zr && zl) {   /* drop, once both are really held; until then slow to a hover */
        if (!g_both_since) g_both_since = now;
        if (now - g_both_since >= DROP_HOLD_MS && idle) {
            w64(E + E_MOTION, idle);
            g_takeoff = 0;
            g_both_since = 0;
            goto still;
        }
    }
    float was = g_fly_vy;
    fly_speed(zr && !zl ? 1 : zl && !zr ? -1 : 0, dt);
    if (g_fly_vy != 0.0f || was != 0.0f) {   /* moving, or just stopped: once more, so the hover holds the height */
        g_fly_wrote = g_fly_vy / g_fly_unit;
        wf(E + E_VY, g_fly_wrote);
    }
    if (!zl || zr) goto out;
    descending = 1;   /* descending: land once standing on something */
    d = y - g_ref_y;
    if (d < 0) d = -d;
    if (!g_descending || d >= 1.0f) {
        g_ref_y = y;
        g_still_since = now;
    } else if (now - g_still_since >= LAND_STILL_MS && idle) {
        w64(E + E_MOTION, idle);
        g_hop_until = now + HOP_MS;
        g_takeoff = 0;
        descending = 0;
        g_fly_vy = 0, g_fly_wrote = 0;
    }
    goto out;
still:   /* not flying (or not under the mod's control): no speed carried into the next flight */
    g_fly_vy = 0, g_fly_wrote = 0;
out:
    g_descending = descending;
}

/* ---------------------------------------------------------------- abilities (1.3)
 * The residents' specialties are actions (Burn 700, Water 703, Grow 706) whose handlers apply the effect for residents only: the
 * handler's execute call checks that its owner is one (vfunc 0x1D8), and the game fires it only for characters that are not the
 * player (main+0x584AE0). Asked for by the player, the same action plays the species' animation and nothing else. So the ability
 * plays that animation and, a moment later, calls the effect itself on the cell in front of the player, found the way the game finds
 * the target of the player's own moves (main+0x2E19A0: the cell the player stands in, one step in the direction it faces):
 *   Grow   FN_GROW(farm, &cell): every crop and growable plant in a plus shape around the cell grows a stage, each once (the game
 *          marks it), as when a resident uses Grow
 *   Burn   FN_OBJECT_ACT(objects, &a resident's id, cell, 120): the object placed at the cell reacts to being burnt, as by a
 *          resident's Burn. The burner must be one of the town's Pokemon: a campfire (main+0x7648EC) lights only for an id whose
 *          top nibble is 2 and puts itself out for a player's (1). The id of a resident of the same species is used, else any.
 *   Water  sludge not bubbled yet in reach (FN_HAS_LAYER finds block kind 8): Bubble, with its own animation (action 705's handler
 *          run with a town Pokemon as its owner: 13 cells around, as Piplup does on Bleak Beach); otherwise FN_WATER(&cell, ...),
 *          the Water Gun's hit: waters the soil, plants and basins there and washes bubbled sludge away
 *   Generate  FN_OBJECT_ACT(objects, &a resident's id, cell, 122): the light or machine placed there is powered (Mareep's 709)
 * Grow and Burn try the cell at the player's height, then one lower and one higher; Water the ground under it first. The test slot (below) runs single steps that a
 * script on the PC writes into the game's memory, to try cells and actions without a rebuild. */
#define ABILITY_EFFECT_MS   700   /* from the animation's start to the effect */
#define ABILITY_COOLDOWN_MS 600
/* Some specialty actions never finish on the player (Grow 706 stays "playing" for good: the end comes from the resident's job code),
   and while one is listed as playing the game refuses the next action, so the ability worked once until a jump cancelled it. So the
   action the ability started is ended with the game's own cancel once its effect is done: at once when the ability is used again,
   else ABILITY_END_MS after its start (longer than any specialty animation on the player, Water's 2.4 s the longest). */
#define ABILITY_END_MS     3000

typedef struct { int16_t x, y, z; int dir; float px, py, pz, yaw; } Target;
static int g_ab_phase;   /* 1: the animation plays, the effect comes at g_ab_at */
static int g_ab_kind;
static uint64_t g_ab_at, g_ab_ready_at;
static uint16_t g_ab_action;   /* the action the last use started, while the controller may still list it as playing (0: none) */
static uint64_t g_ab_started;
static Target g_ab_target;
static int g_ab_bubble;   /* Water: this use is a Bubble on sludge, not the Water Gun */

static float f32_at(const uint8_t *b) {
    union { uint8_t b[4]; float f; } u;
    for (int i = 0; i < 4; i++) u.b[i] = b[i];
    return u.f;
}
static int sane(float v) { return v == v && v < 1e7f && v > -1e7f; }
#ifdef PAP_SWITCH
#define tell(text) ((void)0)
#else
static void tell(const char *text) {
    if (atomic_load(&g_messages) && MT_HOST_HAS(H, notify) && H->notify) H->notify(M, text, 2.5);
}
#endif

/* The cell in front of the player, as main+0x2E19A0 finds it: position (vfunc 0x140) and yaw (vfunc 0x18) from the game, the
   cell = (x + 102400) / 100, y / 100, (z + 102400) / 100, plus one step in the facing quarter (0 = +z, 1 = +x, 2 = -z, 3 = -x). */
static int target_front(uint64_t P, Target *t) {
    static const int8_t DX[4] = {0, 1, 0, -1}, DZ[4] = {1, 0, -1, 0};
    MtCall c;
    uint64_t f = vfunc(P, VF_POSITION);
    memset(&c, 0, sizeof c);
    c.x[0] = P;
    if (!f || H->call_guest(f, &c) != MT_OK) return 0;
    float x = f32_at(c.v[0]), y = f32_at(c.v[0] + 4), z = f32_at(c.v[0] + 8);
    f = vfunc(P, VF_YAW);
    memset(&c, 0, sizeof c);
    c.x[0] = P;
    if (!f || H->call_guest(f, &c) != MT_OK) return 0;
    float yaw = f32_at(c.v[0]), a = yaw < 0 ? -yaw : yaw;
    if (!sane(x) || !sane(y) || !sane(z) || !sane(yaw) || y < 0) return 0;
    int dir = yaw >= 0.7853982f && yaw < 2.3561945f ? 1 : yaw > -2.3561945f && yaw <= -0.7853982f ? 3 : a >= 2.3561945f ? 2 : 0;
    t->dir = dir;
    t->x = (int16_t)((int)((x + 102400.0f) / 100.0f) + DX[dir]);
    t->y = (int16_t)(int)(y / 100.0f);
    t->z = (int16_t)((int)((z + 102400.0f) / 100.0f) + DZ[dir]);
    t->px = x, t->py = y, t->pz = z, t->yaw = yaw;
    return 1;
}

static uint16_t action_now(uint64_t P) {
    uint64_t ctl = r64(P + P_ACTIONS);
    uint16_t a = 0xFFFF;
    if (ctl) r16(ctl + A_CURRENT, &a);
    return a;
}
/* The game's own rule (main+0x27DA60): the player starts a new action while none plays, or an idle one (100, 101, 103, 318). */
static int action_free(uint16_t a) { return a == 0 || a == 100 || a == 101 || a == 103 || a == 318; }
static int request_action(uint64_t P, uint16_t id) {   /* 1 started, 0 refused, -1 the call failed */
    uint64_t f = vfunc(P, VF_REQUEST);
    MtCall c;
    memset(&c, 0, sizeof c);
    c.x[0] = P, c.x[1] = id, c.x[4] = 1;   /* (player, id, 0, 0, 1, 0, 0, 0), as the game's move start asks */
    if (!f || H->call_guest(f, &c) != MT_OK) return -1;
    return (int)(c.x[0] & 1);
}
/* Ends the action the ability started if the controller still lists it as playing: 1 ended, 0 nothing to end, -1 the call failed */
CAVE2_FN static int end_ability_action(uint64_t P, const char *why) {
    uint64_t ctl = r64(P + P_ACTIONS);
    uint16_t a = action_now(P), id = g_ab_action;
    MtCall c;
    g_ab_action = 0;
    if (!id || !ctl || a != id) return 0;
    memset(&c, 0, sizeof c);
    c.x[0] = ctl, c.x[1] = 1;
    if (H->call_guest(MAIN + FN_END_ACTION, &c) != MT_OK) {
        mt_logf(H, M, MT_LOG_WARN, "ability: ending action %u failed", id);
        return -1;
    }
    a = action_now(P);
    mt_logf(H, M, MT_LOG_INFO, "ability: action %u was still playing (%s): ended%s", id, why, a == id ? ", but it still plays" : "");
    return a == id ? -1 : 1;
}
CAVE2_FN static int grow_at(int16_t x, int16_t y, int16_t z) {   /* 1 something grew, 0 nothing did, -1 the call failed */
    uint64_t field = r64(MAIN + FIELD);
    int16_t cell[3] = {x, y, z};
    MtCall c;
    if (!field || H->mem_write(MAIN + SLOT + 0x30, cell, sizeof cell) != MT_OK) return -1;
    memset(&c, 0, sizeof c);
    c.x[0] = field + FARM, c.x[1] = MAIN + SLOT + 0x30;
    if (H->call_guest(MAIN + FN_GROW, &c) != MT_OK) return -1;
    return (int)(c.x[0] & 1);
}
/* A town Pokemon (id top nibble 2) to act as: the same species as the player's form when one lives here, else any. 0: none */
CAVE2_FN static uint64_t town_pokemon(uint16_t form) {
    uint64_t t = r64(MAIN + ENTITY_TABLE), any = 0;
    uint16_t id, sp;
    for (int i = 1; t && i < 0x4B; i++) {
        uint64_t e = r64(t + 0x58 + 8ull * i), o = e ? r64(e + 0x10) : 0;
        if (!o || !r16(o + P_ID, &id) || id >> 12 != RESIDENT_IDS || !r64(o + P_ACTIONS)) continue;
        if (r16(o + 0x398C, &sp) && sp == form) return o;
        if (!any) any = o;
    }
    return any;
}
CAVE2_FN static uint16_t burner_id(uint16_t form) {
    uint64_t o = town_pokemon(form);
    uint16_t id = 0;
    if (o) r16(o + P_ID, &id);
    return id;
}
/* The object placed at the cell reacts as to a resident's specialty: kind BURN_HANDLER burns it, POWER_HANDLER powers it */
CAVE2_FN static int burn_at(uint16_t by, int16_t x, int16_t y, int16_t z, uint32_t kind) {   /* 1 the object reacted, 0 not (or none), -1 failed */
    uint64_t objects = r64(MAIN + OBJECTS);
    MtCall c;
    if (!objects || !by || H->mem_write(MAIN + SLOT + 0x36, &by, 2) != MT_OK) return -1;
    memset(&c, 0, sizeof c);
    c.x[0] = objects, c.x[1] = MAIN + SLOT + 0x36, c.x[2] = (uint16_t)x, c.x[3] = (uint16_t)y, c.x[4] = (uint16_t)z, c.x[5] = kind & 0xFF;
    if (H->call_guest(MAIN + FN_OBJECT_ACT, &c) != MT_OK) return -1;
    return (int)(c.x[0] & 1);
}
CAVE2_FN static int water_at(uint64_t P, int16_t x, int16_t y, int16_t z) {   /* 1 something was watered, 0 not, -1 failed */
    int16_t cell[3] = {x, y, z};
    uint16_t id = 0;
    MtCall c;
    if (!r16(P + P_ID, &id) || H->mem_write(MAIN + SLOT + 0x30, cell, sizeof cell) != MT_OK) return -1;
    memset(&c, 0, sizeof c);
    c.x[0] = MAIN + SLOT + 0x30, c.x[1] = 1, c.x[2] = 1, c.x[3] = 0, c.x[4] = id, c.x[5] = 0;   /* as the Water Gun's hit, uncharged */
    if (H->call_guest(MAIN + FN_WATER, &c) != MT_OK) return -1;
    return (int)(c.x[0] & 1);
}
/* Water's Bubble (what Piplup does to the sludge on Bleak Beach): the resident handler's execute, with a town Pokemon's action
   controller as its owner (it checks for one) and the cell as the argument. It reports nothing back: 1 called, -1 failed. */
CAVE2_FN static int bubble_at(uint16_t form, int16_t x, int16_t y, int16_t z) {
    uint64_t o = town_pokemon(form), ctl = o ? r64(o + P_ACTIONS) : 0, gm = r64(MAIN + GAME_MGR), ht = gm ? r64(gm + 0xA8) : 0;
    uint64_t h = ht ? r64(ht + 0x4470 + 8ull * BUBBLE_HANDLER) : 0;
    uint32_t args[5] = {(uint16_t)x, (uint16_t)y, (uint16_t)z, 0, 4};   /* x, y, z, no request to complete, 4 values */
    MtCall c;
    if (!ctl || !h || H->mem_write(MAIN + SLOT + 0x40, args, sizeof args) != MT_OK) return -1;
    memset(&c, 0, sizeof c);
    c.x[0] = h, c.x[1] = ctl, c.x[2] = MAIN + SLOT + 0x40;
    return H->call_guest(MAIN + FN_BUBBLE, &c) == MT_OK ? 1 : -1;
}
/* 1 when sludge that has not been bubbled lies where a Bubble at the cell reaches: the cells with |dx| + |dz| < 3, at the cell's
   height and one lower (the area Bubble's handler works on). */
CAVE2_FN static int sludge_at(int16_t x, int16_t y, int16_t z) {
    uint64_t world = r64(MAIN + WORLD);
    uint8_t kind = SLUDGE;
    if (!world || H->mem_write(MAIN + SLOT + 0x38, &kind, 1) != MT_OK) return 0;
    for (int dy = -1; dy <= 0; dy++)
        for (int dx = -2; dx <= 2; dx++)
            for (int dz = -2; dz <= 2; dz++) {
                int16_t cell[3] = {(int16_t)(x + dx), (int16_t)(y + dy), (int16_t)(z + dz)};
                MtCall c;
                if ((dx < 0 ? -dx : dx) + (dz < 0 ? -dz : dz) > 2) continue;
                if (H->mem_write(MAIN + SLOT + 0x30, cell, sizeof cell) != MT_OK) return 0;
                memset(&c, 0, sizeof c);
                c.x[0] = world, c.x[1] = MAIN + SLOT + 0x38, c.x[2] = MAIN + SLOT + 0x30;
                if (H->call_guest(MAIN + FN_HAS_LAYER, &c) == MT_OK && (c.x[0] & 1)) return 1;
            }
    return 0;
}

/* Flying: the species has a hover motion; in flight: the current motion is a flying one (as fly() tells them) */
static int motion_kind(uint64_t rec, uint8_t *kind) {
    uint64_t info = rec ? r64(rec + 8) : 0;
    return info && rd(info, kind, 1);
}
static int can_fly(void) {
    uint64_t t = r64(MAIN + ENTITY_TABLE), E = t ? r64(t + 0x58) : 0, set = E ? r64(E + E_MSET) : 0, recs = set ? r64(set + 0xC8) : 0;
    uint32_t count = 0;
    uint8_t kind = 0;
    if (!recs || !rd(set + 0xD0, &count, 4) || count < MOTION_HOVER + 1) return 0;
    return motion_kind(r64(recs + 8 * MOTION_HOVER), &kind) && kind == INFO_FLYING;
}
static int in_flight(void) {
    uint64_t t = r64(MAIN + ENTITY_TABLE), E = t ? r64(t + 0x58) : 0;
    uint8_t kind = 0;
    return E && motion_kind(r64(E + E_MOTION), &kind) && kind == INFO_FLYING;
}

static void ability_effect(uint64_t P, int kind, const Target *t) {
    static const int DY[3] = {0, -1, 1}, DY_WATER[3] = {-1, 0, 1};
    static const char *const DONE[] = {"Grow: the plants grew", "Burn: it worked", "Water: watered", "Generate: powered"};
    static const char *const NONE[] = {"Grow: nothing in front of you to grow (or it grew already)", "Burn: nothing in front of you burns",
                                       "Water: sprayed (no soil or plants to water in front of you)", "Generate: nothing in front of you to power"};
    uint16_t form = atomic_load(&g_form), by = 0;
    if (kind == AB_BURN || kind == AB_GENERATE) {
        by = burner_id(form);
        if (!by) {
            mt_logf(H, M, MT_LOG_INFO, "ability %s: no Pokemon lives in the town to act as", AB_NAMES[kind]);
            tell("This ability needs a Pokemon living in your town");
            return;
        }
    }
    for (int i = 0; i < 3; i++) {
        int16_t y = (int16_t)(t->y + (kind == AB_WATER ? DY_WATER[i] : DY[i]));
        int r = kind == AB_GROW ? grow_at(t->x, y, t->z)
              : kind == AB_BURN ? burn_at(by, t->x, y, t->z, BURN_HANDLER)
              : kind == AB_GENERATE ? burn_at(by, t->x, y, t->z, POWER_HANDLER) : water_at(P, t->x, y, t->z);
        if (r < 0) {
            mt_logf(H, M, MT_LOG_WARN, "ability %s: the game call failed", AB_NAMES[kind]);
            return;
        }
        if (r) {
            mt_logf(H, M, MT_LOG_INFO, "ability %s: worked at (%d, %d, %d)%s", AB_NAMES[kind], t->x, y, t->z, by ? " (as a town Pokemon)" : "");
            tell(DONE[kind]);
            return;
        }
    }
    mt_logf(H, M, MT_LOG_INFO, "ability %s: nothing at (%d, %d to %d, %d)", AB_NAMES[kind], t->x, t->y - 1, t->y + 1, t->z);
    tell(NONE[kind]);
}
/* Ends the game's human ZR action (interacting on, isDitto 0) so the ability can start: 1 ended */
static int end_human_zr(uint64_t P) {
    uint64_t ctl = r64(P + P_ACTIONS);
    MtCall c;
    if (!ctl) return 0;
    memset(&c, 0, sizeof c);
    c.x[0] = ctl, c.x[1] = 1;
    return H->call_guest(MAIN + FN_END_ACTION, &c) == MT_OK && action_now(P) != ACT_HUMAN_ZR;
}
static void ability_start(uint64_t P, uint64_t now) {
    int kind = atomic_load(&g_ability), ok;
    uint16_t a = action_now(P), form = atomic_load(&g_form);
    Target t;
    if (kind < 0) {   /* Auto: the Pokemon's own ability */
        for (int i = 0; i < ABILITY_COUNT; i++)
            if (ABILITY_OF[i].id == form) kind = ABILITY_OF[i].ability;
        if (kind < 0) {
#ifndef PAP_SWITCH
            char m[120];
            snprintf(m, sizeof m, "%s has no ability this mod can use yet", form_name(form));
            tell(m);
#endif
            return;
        }
    }
    if (in_flight()) {
        tell("Land first to use the ability");
        return;
    }
    if (!action_free(a) && g_ab_action && a == g_ab_action && end_ability_action(P, "used again") > 0) a = action_now(P);
    if (a == ACT_HUMAN_ZR && end_human_zr(P)) a = action_now(P);   /* the game saw ZR first (no pad_block on a Switch) */
    if (!action_free(a)) {
        mt_logf(H, M, MT_LOG_INFO, "ability %s: busy (action %u)", AB_NAMES[kind], a);
        return;
    }
    memset(&t, 0, sizeof t);
    if (!target_front(P, &t)) {
        mt_logf(H, M, MT_LOG_WARN, "ability %s: no position or facing from the game", AB_NAMES[kind]);
        return;
    }
    static const uint16_t ACT[] = {ACT_GROW, ACT_BURN, ACT_WATER, ACT_GENERATE};
    g_ab_bubble = kind == AB_WATER && sludge_at(t.x, t.y, t.z);   /* sludge not bubbled yet: Bubble it, else the Water Gun */
    ok = request_action(P, g_ab_bubble ? ACT_BUBBLE : ACT[kind]);
    if (ok <= 0 && g_ab_bubble) ok = request_action(P, ACT_WATER);   /* no Bubble animation: the water one */
    a = action_now(P);   /* what the request started (the Bubble may have fallen back to Water's) */
    g_ab_action = ok > 0 && !action_free(a) && a != 0xFFFF ? a : 0, g_ab_started = now;
    mt_logf(H, M, MT_LOG_INFO, "ability %s: animation %s, cell in front (%d, %d, %d), facing %d (player at %.0f %.0f %.0f, yaw %.2f)",
            g_ab_bubble ? "Water (Bubble)" : AB_NAMES[kind], ok > 0 ? "started" : "refused", t.x, t.y, t.z, t.dir, t.px, t.py, t.pz, t.yaw);
    g_ab_kind = kind, g_ab_target = t, g_ab_phase = 1, g_ab_at = now + ABILITY_EFFECT_MS;
}
static void abilities(uint64_t P) {
    uint64_t now = now_ms();
    int press = g_ab_press;
    g_ab_press = PRESS_NONE;
    if (g_ab_phase == 1 && now >= g_ab_at && g_ab_kind == AB_WATER && g_ab_bubble) {   /* Water on sludge: Bubble it */
        const Target *t = &g_ab_target;
        int r = bubble_at(atomic_load(&g_form), t->x, t->y, t->z);
        mt_logf(H, M, MT_LOG_INFO, "ability Water: Bubble around (%d, %d, %d)%s", t->x, t->y, t->z, r < 0 ? ": no town Pokemon to act as" : "");
        tell(r < 0 ? "Bubble needs a Pokemon living in your town" : "Water: Bubble on the sludge (now wash it with Water)");
        g_ab_phase = 0, g_ab_bubble = 0;
        g_ab_ready_at = now + ABILITY_COOLDOWN_MS;
        return;
    }
    if (g_ab_phase) {
        if (now >= g_ab_at) {
            g_ab_phase = 0;
            ability_effect(P, g_ab_kind, &g_ab_target);
            g_ab_ready_at = now + ABILITY_COOLDOWN_MS;
        }
        return;
    }
    if (g_ab_action) {   /* the effect is done: the action finished by itself, something else replaced it, or it is left playing */
        uint16_t a = action_now(P);
        if (a != g_ab_action) g_ab_action = 0;
        else if (now >= g_ab_started + ABILITY_END_MS) end_ability_action(P, "past its animation");
    }
    if (!press || now < g_ab_ready_at) return;
    if (press == PRESS_ZR && atomic_load(&g_fly) && can_fly()) return;   /* a flying Pokemon's ZR flies */
    ability_start(P, now);
}

/* The test slot. A script on the PC writes SLOT_MAGIC at SLOT, the arguments, and last a step number at SLOT + 4; the player's next
 * update runs it, writes the result back and clears the step. Layout: +0 u32 magic, +4 u16 step, +6 u16 argument, +8 s16 x, y, z,
 * +0x10 s32 result, +0x14 u32 steps run, +0x18 f32 player x, y, z, yaw, +0x28 s16 the cell in front x, y, z, +0x2E u16 the action
 * playing, +0x30 the cell this mod hands to the game. Steps: 1 Grow at (x, y, z); 2 burn the object at (x, y, z), the argument as
 * w5, as a town Pokemon; 3 request action <argument>; 4 report only (result: the direction faced); 5 the ability, as if its button
 * was pressed; 6 water (x, y, z); 7 turn into form <argument> (0: back); 8 Bubble around (x, y, z). Step 2 with argument 122 powers. */
static void test_slot(uint64_t P) {
    uint32_t magic = 0, done = 0;
    uint16_t step = 0, arg = 0, a;
    int16_t cell[3] = {0, 0, 0}, front[3];
    int32_t result = -1;
    Target t;
    if (!rd(MAIN + SLOT, &magic, 4) || magic != SLOT_MAGIC || !r16(MAIN + SLOT + 4, &step) || !step) return;
    r16(MAIN + SLOT + 6, &arg);
    rd(MAIN + SLOT + 8, cell, sizeof cell);
    memset(&t, 0, sizeof t);
    int have = target_front(P, &t);
    switch (step) {
    case 1: result = grow_at(cell[0], cell[1], cell[2]); break;
    case 2: result = burn_at(burner_id(atomic_load(&g_form)), cell[0], cell[1], cell[2], arg); break;
    case 6: result = water_at(P, cell[0], cell[1], cell[2]); break;
    case 8: result = bubble_at(atomic_load(&g_form), cell[0], cell[1], cell[2]); break;
    case 7:   /* turn into form <argument> (0: back to the player's own character), queued like the menu's choice */
        if (arg) atomic_store(&g_selected, arg);
        want(arg, 0);
        result = 1;
        break;
    case 3: result = request_action(P, arg); break;
    case 4: result = have ? t.dir : -1; break;
    case 5:
        result = atomic_load(&g_form) ? 1 : 0;
        if (result) g_ab_press = PRESS_KEY;
        break;
    default: break;
    }
    a = action_now(P);
    front[0] = t.x, front[1] = t.y, front[2] = t.z;
    float pos[4] = {t.px, t.py, t.pz, t.yaw};
    rd(MAIN + SLOT + 0x14, &done, 4);
    done++;
    H->mem_write(MAIN + SLOT + 0x10, &result, 4);
    H->mem_write(MAIN + SLOT + 0x14, &done, 4);
    H->mem_write(MAIN + SLOT + 0x18, pos, sizeof pos);
    H->mem_write(MAIN + SLOT + 0x28, front, sizeof front);
    H->mem_write(MAIN + SLOT + 0x2E, &a, 2);
    mt_logf(H, M, MT_LOG_INFO, "test slot: step %u (argument %u, cell %d %d %d) -> %d; in front (%d, %d, %d), action %u", step, arg,
            cell[0], cell[1], cell[2], result, front[0], front[1], front[2], a);
    step = 0;
    H->mem_write(MAIN + SLOT + 4, &step, 2);
}

/* Diagnostics: while transformed (and 10 s after), each change of the player's form fields goes to pkp.log. The transition
   animation (+0x378A) the game writes is a constant at each place in its code, so it shows where a form change came from. */
static uint64_t g_trace_until;
static void trace(uint64_t P) {
    static uint16_t last[4];
    static uint8_t lastb[3];
    static int have;
    uint16_t v[4] = {0};
    uint8_t b[3] = {0};
    uint64_t now = now_ms();
    if (atomic_load(&g_form)) g_trace_until = now + 10000;
    if (now >= g_trace_until) { have = 0; return; }
    r16(P + P_FORM_NOW, &v[0]), r16(P + P_FORM_WANT, &v[1]), r16(P + P_REQ_STATE, &v[2]), r16(P + P_REQ_ANIM, &v[3]);
    rd(P + P_REQ_GO, b, 3);   /* +0x378C request, +0x378D isDitto, +0x378E transform motion playing */
    int same = have;
    for (int i = 0; i < 4; i++) same &= v[i] == last[i], last[i] = v[i];
    for (int i = 0; i < 3; i++) same &= b[i] == lastb[i], lastb[i] = b[i];
    have = 1;
    if (same) return;
    mt_logf(H, M, MT_LOG_INFO, "trace f%llu: form %u want %u | request %u anim 0x%x go %u ditto %u playing %u | mod form %u",
            (unsigned long long)(H->frame ? H->frame() : 0), v[0], v[1], v[2], v[3], b[0], b[1], b[2], atomic_load(&g_form));
}

/* ---------------------------------------------------------------- Link Play (1.4)
 * The other players' characters are the same kind of character as the player's and run the same update (h_player_tick sees
 * them too). Each game sends its player's wanted form (P_FORM_WANT, through the form_get vfunc, so a transformed player sends
 * the Pokemon) and the others store it with form_set (main+0x271360, the player state receiver). But a game changes another
 * player's form only by playing that form's transformation action (main+0x2F6FCC), and only the game's own six player forms
 * have one. So the Pokemon arrived and was never applied: the others kept seeing the human, and the actions they received,
 * which are played for the wanted form, did not fit the human model, so it stood still in its idle pose.
 * Here each game shows the other players' forms itself, as it does for its own player: it loads the form's animations (holds,
 * 1.6: before asking for the form, so their model is built once, with them), requests the form on their character, and keeps
 * the stand-up stretch off them (probe). Turning back is requested the same way. The game's own forms are left to the game.
 * Up to 1.5 the form was requested first and the model built a second time once the animations had loaded: in between, the
 * model slot was empty and the game crashed when it read it (see "holds"), which three or four players made far more likely. */
#define REMOTE_MAX 4
#define REMOTE_GONE_MS  5000   /* a character not updated for this long has left: its slot is free again */
#define REMOTE_TRIES       5   /* requests for one form that did not take, before waiting for the next form */
typedef struct {
    _Atomic uint64_t ch;          /* the other player's character (0 = free slot) */
    _Atomic int shown;            /* in one of this mod's forms (read by h_probe on any thread) */
    _Atomic uint64_t seen;        /* its last update */
    uint16_t id, v[4];            /* its character id; the form fields as last logged */
    uint8_t b[3];
    uint16_t asked;               /* the form last requested for it here */
    uint16_t waiting;             /* the form whose animations it waits for (logged once) */
    int tries;
    uint64_t last_request;
    Holds holds;                  /* as g_holds: its update and model setup only */
} Remote;
static Remote g_remote[REMOTE_MAX];

static int online(void) {
    uint64_t gm = r64(MAIN + GAME_MGR);
    uint8_t f = 0;
    return gm && rd(gm + 0x90, &f, 1) && (f & 1);   /* GameMgr.online, bit 0 */
}
static int remote_slot(uint64_t ch) {
    for (int i = 0; ch && i < REMOTE_MAX; i++)
        if (atomic_load(&g_remote[i].ch) == ch) return i;
    return -1;
}
/* A slot is let go without releasing its holds: the character is gone (or the session over), and releasing a motion set while
   a model might still use it would unbind its animations under it. The packages stay loaded until the world reset, that is all. */
static void remote_free(int i) {
    Remote *R = &g_remote[i];
    atomic_store(&R->shown, 0);
    R->id = 0, R->asked = R->waiting = 0, R->tries = 0, R->last_request = 0;
    memset(&R->holds, 0, sizeof R->holds);
    atomic_store(&R->ch, 0);
}
static int remote_claim(uint64_t ch, uint16_t id) {
    for (int i = 0; i < REMOTE_MAX; i++) {
        uint64_t none = 0;
        if (!atomic_compare_exchange_strong(&g_remote[i].ch, &none, ch)) continue;
        Remote *R = &g_remote[i];
        R->id = id;
        R->v[0] = 0xFFFF;   /* log the first state */
        atomic_store(&R->seen, now_ms());
        mt_logf(H, M, MT_LOG_INFO, "remote player id 0x%x", id);
        return i;
    }
    return -1;
}
/* From the player's own update: slots of characters that stopped updating (a player left) are freed; all of them once the
   session is over. */
static void remote_sweep(void) {
    int on = online();
    uint64_t now = now_ms();
    for (int i = 0; i < REMOTE_MAX; i++) {
        if (!atomic_load(&g_remote[i].ch)) continue;
        if (on && now - atomic_load(&g_remote[i].seen) < REMOTE_GONE_MS) continue;
        mt_logf(H, M, MT_LOG_INFO, "remote player id 0x%x: gone", g_remote[i].id);
        remote_free(i);
    }
}
static int any_remote_shown(void) {
    for (int i = 0; i < REMOTE_MAX; i++)
        if (atomic_load(&g_remote[i].shown)) return 1;
    return 0;
}
static int remote_shown(uint64_t ch) {
    int i = remote_slot(ch);
    return i >= 0 && atomic_load(&g_remote[i].shown);
}

static void remote_request(Remote *R, uint64_t ch, uint16_t form, uint64_t now) {
    w16(ch + P_REQ_STATE, form);
    w16(ch + P_REQ_ANIM, TRANSFORM_ANIM);
    w8(ch + P_REQ_GO, 1);
    R->last_request = now;
}

/* The model setup of another player's character (h_char_setup): as for the player, a model in one of this mod's forms is built
   only with the form's animations loaded, else as the human until they are (remote_tick then asks for the form again). */
static void remote_model(MtHookCtx *c, uint64_t ch, uint16_t res) {
    int i = remote_slot(ch);
    if (i < 0) return;
    Remote *R = &g_remote[i];
    uint16_t cur = 0;
    r16(ch + P_FORM_NOW, &cur);   /* the model setup builds the current form (vfunc 0x1D0) */
    mt_logf(H, M, MT_LOG_INFO, "remote model id 0x%x: animation resource %u (form %u)", R->id, res, cur);
    w16(H->reg_get(c, 25) + 0xE94, res);   /* as in h_char_setup: the store this hook point replaces, first */
    if (!mod_form(cur) || !prepare_model(c, &R->holds, ch, cur)) return;
    mt_logf(H, M, MT_LOG_INFO, "remote player id 0x%x: %s (form %u) built before its animations were loaded: as the human until they are",
            R->id, form_name(cur), cur);
    R->last_request = now_ms();
}

/* Another player's update (h_player_tick): show the form that player wants when it is one of this mod's, once its animations are
   loaded, or turn them back from one. One request at a time, REQUEST_GAP_MS apart, as for the player; a form that does not take
   is tried REMOTE_TRIES times. */
static void remote_tick(uint64_t ch) {
    uint16_t id = 0;
    if (!online() || !r16(ch + P_ID, &id)) return;
    int i = remote_slot(ch);
    if (i >= 0 && g_remote[i].id != id) {   /* the character was freed and made again for another player */
        remote_free(i);
        i = -1;
    }
    if (i < 0) {
        if ((id & 0x800) || (id >> 12) != PLAYER_IDS) return;   /* not a player's id */
        if ((i = remote_claim(ch, id)) < 0) return;
    }
    Remote *R = &g_remote[i];
    uint64_t now = now_ms();
    atomic_store(&R->seen, now);

    uint16_t v[4] = {0};   /* form, want, request, anim */
    uint8_t b[3] = {0};    /* go, isDitto, transform motion playing */
    r16(ch + P_FORM_NOW, &v[0]), r16(ch + P_FORM_WANT, &v[1]), r16(ch + P_REQ_STATE, &v[2]), r16(ch + P_REQ_ANIM, &v[3]);
    rd(ch + P_REQ_GO, b, 3);
    int same = 1;
    for (int k = 0; k < 4; k++) same &= v[k] == R->v[k], R->v[k] = v[k];
    for (int k = 0; k < 3; k++) same &= b[k] == R->b[k], R->b[k] = b[k];
    if (!same)
        mt_logf(H, M, MT_LOG_INFO, "remote trace id 0x%x f%llu: form %u want %u | request %u anim 0x%x go %u ditto %u playing %u", R->id,
                (unsigned long long)(H->frame ? H->frame() : 0), v[0], v[1], v[2], v[3], b[0], b[1], b[2]);

    uint16_t cur = v[0], want = v[1], pending = v[2];
    atomic_store(&R->shown, mod_form(cur) || mod_form(want));
    holds_tick(&R->holds, cur, want, b[0] ? pending : 0, now);
    if (want != R->asked) R->tries = 0;
    if (want == cur || b[0] || (pending >= 1 && pending <= FORM_MAX)) return;   /* nothing to do, or a change under way */
    if (!mod_form(want) && !mod_form(cur)) return;                              /* the game's own forms: the game does it */
    if (want == 0 || want > FORM_MAX || R->tries >= REMOTE_TRIES) return;
    if (mod_form(want)) {   /* its animations first */
        Hold *h = hold_take(&R->holds, want, 0, now);
        int st = h ? hold_ready(h, now) : LOAD_WAIT;
        if (st == LOAD_FAILED) {
            mt_logf(H, M, MT_LOG_WARN, "remote player id 0x%x: %s (form %u) did not load, not shown", R->id, form_name(want), want);
            R->asked = want, R->tries = REMOTE_TRIES;
            return;
        }
        if (st == LOAD_WAIT) {
            if (R->waiting != want)
                mt_logf(H, M, MT_LOG_INFO, "remote player id 0x%x wants %s (form %u): loading it first%s", R->id, form_name(want), want,
                        h ? "" : " (every hold in use)");
            R->waiting = want;
            return;
        }
    }
    R->waiting = 0;
    if (now - R->last_request < REQUEST_GAP_MS) return;
    if (++R->tries == REMOTE_TRIES)
        mt_logf(H, M, MT_LOG_INFO, "remote player id 0x%x: form %u does not take, last try", R->id, want);
    R->asked = want;
    if (mod_form(want))
        mt_logf(H, M, MT_LOG_INFO, "remote player id 0x%x is %s (form %u): shown here", R->id, form_name(want), want);
    else
        mt_logf(H, M, MT_LOG_INFO, "remote player id 0x%x turns from %s into form %u", R->id, form_name(cur), want);
    remote_request(R, ch, want, now);
}

/* main+0x8D12C0 (x0 = the animation package manager), entry: releases every motion set at once, down to no uses, so they lose
   their animations (each set: FN_MSET_REL(resource, 1)); right after it main+0x8CFE40 unloads the animation packages. The game
   calls it only from its world reset (main+0xB6320), which also runs when a Link Play session ends. The holds this mod took (the
   player's form and the other players') are gone with it, so it forgets them, without releasing anything: a release now would
   come out of the next world's own holds. Before 1.5 it did not, and after the session:
   - a Pokemon the player was turned into still counted as loaded, so turning into it again skipped loading its animations
     (the host's broken model until it changed Pokemon), and
   - a hold taken on the human animations while the game had turned the player human (the session's end message) was released
     after the reset from the game's own: the human model broke until a restart (the guest). char_setup no longer takes it.
   1.6: every hold taken before the reset carries the old g_reset_gen and is dropped, unreleased, by its owner's next look. */
static int h_motion_reset(MtHookCtx *c, void *u) {
    (void)c, (void)u;
    int others = 0;
    atomic_fetch_add(&g_reset_gen, 1);
    for (int i = 0; i < REMOTE_MAX; i++)
        if (atomic_load(&g_remote[i].ch)) remote_free(i), others++;
    mt_logf(H, M, MT_LOG_INFO, "the game reset every Pokemon's animations (a new world: the end of a Link Play session, a reload): "
            "forgetting the player's and %d other player(s)'", others);
    return MT_CONTINUE;
}

static int h_player_tick(MtHookCtx *c, void *u) {   /* blr x8 near the top of the player's update: x0 = the character */
    (void)u;
    uint64_t P = player(), ch = H->reg_get(c, 0);
    if (P && ch && ch != P) remote_tick(ch);
    if (!P || ch != P) return MT_CONTINUE;
    remote_sweep();
    trace(P);
    buttons(P);
    load_tick(P);
    keep_form(P);
    interact_tick(P);
    uint16_t cur = 0;
    r16(P + P_FORM_NOW, &cur);
    holds_tick(&g_holds, cur, atomic_load(&g_form), g_load, now_ms());
#ifndef PAP_SWITCH
    test_slot(P);
#endif
    if (!g_menu && atomic_load(&g_form) && atomic_load(&g_fly)) fly(P);
    if (!g_menu && atomic_load(&g_form) && atomic_load(&g_abilities)) abilities(P);
    else g_ab_phase = 0, g_ab_action = 0;
    return MT_CONTINUE;
}

/* ---------------------------------------------------------------- the form patches (v0.3 - v0.5) */
static int h_form_get(MtHookCtx *c, void *u) {   /* entry of the desired-form getter (x0 = character): return the form */
    (void)u;
    uint16_t f = atomic_load(&g_form);
    if (!f || !is_player(H->reg_get(c, 0))) return MT_CONTINUE;
    H->reg_set(c, 0, f);
    return MT_HANDLED;
}
static int h_form_set(MtHookCtx *c, void *u) {   /* entry of the desired-form setter (x0 = character, w1): store the form instead */
    (void)u;
    uint16_t f = atomic_load(&g_form);
    if (f && is_player(H->reg_get(c, 0))) H->reg_set(c, 1, f);
    return MT_CONTINUE;
}
/* RequestState(x0 = character + P_STATE, w1 state): drop "back to human" for the player. While transformed, the game's other
   requests for the player are logged once per state and caller, to find what changes the form (pkp.log). */
static int h_request_state(MtHookCtx *c, void *u) {
    (void)u;
    uint16_t form = atomic_load(&g_form);
    uint64_t P = player();
    if (!form || !P || H->reg_get(c, 0) != P + P_STATE) return MT_CONTINUE;
    uint32_t state = (uint32_t)H->reg_get(c, 1) & 0xFFFF;
    uint64_t from = H->reg_get(c, 30);
    static uint32_t last_state;
    static uint64_t last_from;
    if (state != form && (state != last_state || from != last_from)) {
        last_state = state, last_from = from;
        mt_logf(H, M, MT_LOG_INFO, "the game asked to turn the player into form %u (from main+0x%llx)%s", state,
                (unsigned long long)(from >= MAIN ? from - MAIN : from), state == HUMAN ? ": ignored" : "");
    }
    return state == HUMAN ? MT_HANDLED : MT_CONTINUE;
}
/* main+0x455580 (w0 = local player slot 0 / 1, ...) -> w0 1: turns that player human for an interaction, writing "state 1,
   animation 0x3AF" into its state machine itself (RequestState inlined). Talking to most Pokemon calls it every frame, and the
   conversation waits for the human form (keeping the player transformed here left it stuck). So the game gets its way: this
   only notes the time, and keep_form turns the player back into the Pokemon once the interaction is over. */
static int h_to_human(MtHookCtx *c, void *u) {
    (void)u;
    uint64_t P = player(), g = r64(MAIN + PLAYER_GLOBAL);
    if (!atomic_load(&g_form) || !P || !g || r64(g + (((uint32_t)H->reg_get(c, 0) & 0xFF) ? 0x38 : 0x30)) != P) return MT_CONTINUE;
    uint64_t now = now_ms(), last = atomic_load(&g_interaction_at), from = H->reg_get(c, 30);
    if (!last || now - last > INTERACTION_QUIET_MS)
        mt_logf(H, M, MT_LOG_INFO, "an interaction turns the player human (from main+0x%llx)", (unsigned long long)(from >= MAIN ? from - MAIN : from));
    atomic_store(&g_interaction_at, now);
    return MT_CONTINUE;
}
/* Animation condition 0x56 = not (wall probe). Function entry: (x0 = &controller, w1 = mode); returns probe ^ (mode == 1).
   For the player while transformed, and for another player shown in one of this mod's forms, the probe counts as true, so the
   idle -> stand-up transition never fires. The probe (main+0x6D5374) finds the character as entity [ENTITY_TABLE] + 0x58 +
   8 * ([[controller] + 8] + 0x1C), whose +0x10 is the character; the player's entity is index 0. */
static int h_probe(MtHookCtx *c, void *u) {
    (void)u;
    int local = atomic_load(&g_form) != 0, remote = any_remote_shown();
    if (!local && !remote) return MT_CONTINUE;
    uint64_t ctl = r64(H->reg_get(c, 0)), owner = ctl ? r64(ctl + 8) : 0;
    uint16_t idx = 0xFFFF;
    if (!owner || !r16(owner + 0x1C, &idx) || idx >= 0x4B) return MT_CONTINUE;
    if (!(local && idx == 0)) {
        uint64_t t = remote ? r64(MAIN + ENTITY_TABLE) : 0, e = t ? r64(t + 0x58 + 8ull * idx) : 0;
        if (!e || !remote_shown(r64(e + 0x10))) return MT_CONTINUE;
    }
    H->reg_set(c, 0, (uint32_t)H->reg_get(c, 1) == 1 ? 0 : 1);
    return MT_HANDLED;
}

/* The face (1.6.1). Each frame the game picks a player character's face (main+0x266278) and sets it on the model (main+0x71B770:
   the model slot's +0xBE8, 1..30). In water, unless the form is Ditto's Magnet Rise one, it forces face 22, the human's and Surf
   Ditto's underwater face. A Pokemon's model has no such face: the eyes of Froakie, Greninja, Cramorant and others went blank
   while swimming (measured live: +0xBE8 22 swimming, 1 on land, nothing else of the model changed). Hook at main+0x2666C4, just
   before the call: x19 = the character, x20 = its face state (+0x10 = the face chosen before the water override), w22 = the face.
   For a character in one of this mod's forms (the player or another player) face 22 becomes the face it would have had. */
#define FACE_UNDERWATER 22
#define FACE_STATE_BASE 0x10
static int h_face(MtHookCtx *c, void *u) {
    (void)u;
    uint64_t ch = H->reg_get(c, 19), st = H->reg_get(c, 20);
    uint16_t form = 0;
    uint8_t face = 1;
    if (((uint32_t)H->reg_get(c, 22) & 0xFF) != FACE_UNDERWATER || !r16(ch + P_FORM_NOW, &form) || !mod_form(form)) return MT_CONTINUE;
    if (!rd(st + FACE_STATE_BASE, &face, 1) || face < 1 || face > 30 || face == FACE_UNDERWATER) face = 1;
    H->reg_set(c, 22, face);
    return MT_CONTINUE;
}

/* 1.7.1: the bag (and the other buttons) while flying. The player's button handler FUN_710031618c returns early while the body is
   in the air (bit 0 of u16 [P+0x18A8]+0xB8; 0x0002 standing, 0x000F hovering), unless the bag is already open (P+0x53A8 1) or the
   player is the Ditto blob (isDitto 1, which the mod clears for interacting). Found live 2026-11-23: write watchpoint on P+0x53A8
   (the bag) -> FUN_71002F8168 <- 0x318E60 <- 0x31618C. Hook point: main+0x3164A4 `tbz w8, #0, ...` with w8 = those flags and
   x23 = the player: for the local player flying as the mod's Pokemon, the game sees bit 0 clear and handles the buttons as on
   the ground. The flags themselves (physics) are not touched. */
#define BODY_AIR 1u
static int h_air_menu(MtHookCtx *c, void *u) {
    (void)u;
    uint64_t P = player();
    if (!P || H->reg_get(c, 23) != P || !atomic_load(&g_form) || !atomic_load(&g_interact) || !in_flight()) return MT_CONTINUE;
    uint64_t w8 = H->reg_get(c, 8);
    if (w8 & BODY_AIR) H->reg_set(c, 8, w8 & ~(uint64_t)BODY_AIR);
    return MT_CONTINUE;
}

/* ---------------------------------------------------------------- entry */
#ifndef PAP_SWITCH
MT_EXPORT int mod_init(const MtHost *host, MtMod *mod) {
    H = host, M = mod;
    MAIN = H->module_base("main");
    if (!MAIN) {
        H->log(M, MT_LOG_ERROR, "no main module");
        return MT_ERR;
    }
    static const struct { const char *point; MtHookFn fn; } hooks[] = {
        {"form_get", h_form_get},       {"form_set", h_form_set}, {"request_state", h_request_state},
        {"probe", h_probe},
        {"char_setup", h_char_setup},   {"player_tick", h_player_tick}, {"to_human", h_to_human},
        {"motion_reset", h_motion_reset}, {"face", h_face}, {"chair_use", h_chair_use}, {"bed_use", h_bed_use},
        {"attach", h_attach},           {"air_menu", h_air_menu},
    };
    for (size_t i = 0; i < sizeof hooks / sizeof hooks[0]; i++) {
        int rc = H->hook(M, hooks[i].point, hooks[i].fn, NULL);
        if (rc != MT_OK) {
            mt_logf(H, M, MT_LOG_ERROR, "cannot hook %s (%d)", hooks[i].point, rc);
            return MT_ERR;
        }
    }
    read_settings();
    H->on_config_changed(M, on_config, NULL);
    mt_logf(H, M, MT_LOG_INFO, "ready: ZL + L3 turns into %s and back, ZL + D-pad Left / Right picks another, %s or ZL + R3 opens the list; "
            "ZR or ZL + D-pad Down uses the ability (%s%s)", form_name(atomic_load(&g_selected)), H->config_string(M, "key_menu"),
            atomic_load(&g_ability) < 0 ? "the Pokemon's own" : AB_NAMES[atomic_load(&g_ability)], atomic_load(&g_abilities) ? "" : ", off");
    return MT_OK;
}
#else
/* ---------------------------------------------------------------- Switch entry points
 * build_emulator.py puts a branch to a trampoline at each hook point (the same game instructions as mod.toml's); the trampoline saves
 * every register, calls pap_hook_<point>(registers) and then, for MT_CONTINUE, runs the game's own instruction and goes on, or for
 * MT_HANDLED returns from the game's function. switch_host.c sets everything up at the first stop and calls pap_mod_start. */
int pap_ready(void);
void pap_mod_start(const MtHost *host) {
    H = host, M = 0;
    MAIN = H->module_base("main");
    read_settings();
}
#define PAP_POINT(name, fn)     int pap_hook_##name(MtHookCtx *c) { return pap_ready() && MAIN ? fn(c, NULL) : MT_CONTINUE; }
PAP_POINT(form_get, h_form_get)
PAP_POINT(form_set, h_form_set)
PAP_POINT(request_state, h_request_state)
PAP_POINT(probe, h_probe)
PAP_POINT(char_setup, h_char_setup)
PAP_POINT(player_tick, h_player_tick)
PAP_POINT(to_human, h_to_human)
PAP_POINT(motion_reset, h_motion_reset)
PAP_POINT(face, h_face)
PAP_POINT(chair_use, h_chair_use)
PAP_POINT(bed_use, h_bed_use)
PAP_POINT(attach, h_attach)
PAP_POINT(air_menu, h_air_menu)
#endif
