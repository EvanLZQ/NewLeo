"""Every lens-pricing parameter that may change lives here.

`DEFAULTS` holds the shipped values. The single LensPricingSettings row in
the database (admin: Lens pricing settings) overrides them: its typed fields
for the common switches, and its `overrides` JSON for anything else in
DEFAULTS (same keys). Nothing in engine.py hard-codes a price, an index
bracket or a colour list; it reads them from the dict `get_config()` returns.

Business decisions recorded here (see /impl/QUESTIONS.md for open ones):

* enforce_limitation=True   — boss, written answer Q3 (2026-11-15): the
  Limitation S / C columns override the grid. A global switch because the
  boss may drop limitations later (meeting, not decided).
* reader_line="economic", reader_coatings Clear + Blue Light — default for
  boss question 1 (round 3), not yet answered.
* reader range +0.25..+4.50 step 0.25 — written answer R2-5.
* gradient_ignore_dedicated_depths=[80] — default for boss question 3
  (round 3): an 80% gray/brown *gradient* is priced from the general
  "Sun & Tint Colors" block (39.95 at Economic SV 1.50), not from the
  separately priced 80% gray/brown stock-lens block (9.95). Set to [] to
  price gradients exactly like solid tints.
* add range +0.75..+3.50 step 0.25, bifocal/progressive only — P1.
"""
import copy
from decimal import Decimal

DEFAULTS = {
    # ── switches ────────────────────────────────────────────────────────────
    "enforce_limitation": True,
    "max_cyl": "6.00",
    # How many indexes to show on each side of the recommended one (R2-9).
    "neighbor_count": 1,

    # ── ADD (bifocal / progressive prescription entry only; never priced) ──
    "add_min": "0.75",
    "add_max": "3.50",
    "add_step": "0.25",
    "add_required_categories": ["BIFOCAL", "PROGRESSIVE"],

    # ── Readers (ready-made reading glasses) ───────────────────────────────
    "reader_min": "0.25",
    "reader_max": "4.50",
    "reader_step": "0.25",
    "reader_line": "economic",
    "reader_rx_type": "SV_FAR",
    "reader_lens_type": "CLEAR",
    "reader_coatings": [
        {"code": "N", "label": "Clear"},
        {"code": "BLUE", "label": "Blue Light Filtering"},
    ],

    # ── Gradient ───────────────────────────────────────────────────────────
    "gradient_enabled": True,
    # Depths at which a gradient does NOT use a separately priced colour
    # block (e.g. Economic 80% gray/brown stock lens) and uses the general
    # colour block instead. [] = gradient priced exactly like solid.
    "gradient_ignore_dedicated_depths": [80],

    # ── Sheet vocabulary → codes ───────────────────────────────────────────
    "rx_types": {
        "single vision nearsighted": "SV_NEAR",
        "single vision farsighted": "SV_FAR",
        "bifocal": "BIFOCAL",
        "progressive": "PROGRESSIVE",
    },
    "lens_types": {"clear": "CLEAR", "photochromic": "PHOTOCHROMIC", "sun/tint": "SUN", "sun / tint": "SUN"},
    "coatings": {
        "n": "N", "blue light filtering": "BLUE", "blue light": "BLUE",
        "polarized": "POLARIZED", "mirrored": "MIRRORED",
    },
    # Colour column text (lower case, single spaced) → colour codes. A group
    # listed in generic_color_groups is used only when no other block of the
    # same product prices that colour (R2-3(b), 8(c)).
    "color_groups": {
        "n": [],
        "gray, brown": ["gray", "brown"],
        "pink, purple, blue": ["pink", "purple", "blue"],
        "sun & tint colors": ["gray", "brown", "green", "red", "blue", "yellow", "purple"],
        # Polarized "Gray, Brown, Green" = Black Gray, Brown, Gray Green, plus
        # Night Vision Yellow at the same price (R2-4(b), Q10=B).
        "gray, brown, green": ["night-vision-yellow", "gray-green", "black-gray", "brown"],
        # Mirrored = the polarized swatch card minus its first four (R2-4(a)).
        "polarized colors": ["rv-green", "rv-red", "rv-purple", "white-mercury",
                             "rose-gold", "yellow-gold", "blue", "ice-blue"],
    },
    "generic_color_groups": ["sun & tint colors"],

    # ── Storefront vocabulary ──────────────────────────────────────────────
    "categories": [
        {"code": "SINGLE_VISION", "label": "Single Vision", "rx_required": True,
         "description": "Distance or reading. We work out near- or far-sighted from your prescription."},
        {"code": "BIFOCAL", "label": "Bifocal", "rx_required": True,
         "description": "Two viewing areas with a visible line."},
        {"code": "PROGRESSIVE", "label": "Progressive", "rx_required": True,
         "description": "Distance to near with no visible line."},
        {"code": "READERS", "label": "Readers", "rx_required": False,
         "description": "Ready-made reading glasses: pick a magnification."},
        {"code": "NON_RX", "label": "Non-prescription", "rx_required": False,
         "description": "Plano lenses with no correction."},
    ],
    "lens_type_labels": {
        "CLEAR": "Clear", "PHOTOCHROMIC": "Light-responsive (Photochromic)", "SUN": "Sun / Tint",
    },
    "tint_labels": {
        "SOLID": "Solid tint", "GRADIENT": "Gradient tint",
        "MIRRORED": "Mirrored (polarized)", "POLARIZED": "Polarized",
    },
    "coating_labels": {"N": "Standard", "BLUE": "Blue Light Filtering"},
    "depths": [30, 50, 80],
    "color_labels": {
        "gray": "Gray", "brown": "Brown", "green": "Green", "red": "Red", "blue": "Blue",
        "yellow": "Yellow", "purple": "Purple", "pink": "Pink",
        "night-vision-yellow": "Night Vision Yellow", "gray-green": "Gray Green",
        "black-gray": "Black Gray", "rv-green": "RV Green", "rv-red": "RV Red",
        "rv-purple": "RV Purple", "white-mercury": "White Mercury", "rose-gold": "Rose Gold",
        "yellow-gold": "Yellow Gold", "ice-blue": "Ice Blue",
    },
    # Swatch image file names (under the storefront's /lens-swatches/).
    # {depth} is 30/50/80. Missing entries fall back to a plain dot.
    "swatches": {
        "SOLID": "sun_solid-{depth}_{color}.png",
        "GRADIENT": "sun_gradient-{depth}_{color}.png",
        "POLARIZED": "polarized_{color}.png",
        "MIRRORED": "polarized_{color}.png",
        "PHOTOCHROMIC": "photochromic_{color}_stronglight.png",
    },
    "swatch_color_alias": {"gray": {"PHOTOCHROMIC": "grey"}},
}

# Recommendation label texts in the sheet → label code.
LABEL_RECOMMENDED = "RECOMMENDED"
LABEL_AVAILABLE = "AVAILABLE"
LABEL_FREE_UPGRADE = "FREE_UPGRADE"

TYPED_FIELDS = (
    "enforce_limitation", "max_cyl", "neighbor_count",
    "add_min", "add_max", "add_step",
    "reader_min", "reader_max", "reader_step", "reader_line", "reader_coatings",
    "gradient_ignore_dedicated_depths",
)


def defaults():
    return copy.deepcopy(DEFAULTS)


def merge(base, row=None):
    """DEFAULTS + one LensPricingSettings row (or any object/dict with the
    same attributes) → plain dict."""
    cfg = copy.deepcopy(base)
    if row is None:
        return cfg
    get = row.get if isinstance(row, dict) else (lambda k, d=None: getattr(row, k, d))
    overrides = get("overrides") or {}
    for key, value in overrides.items():
        if key in cfg:
            cfg[key] = value
    for key in TYPED_FIELDS:
        value = get(key, None)
        if value is None or value == "":
            continue
        cfg[key] = str(value) if isinstance(value, Decimal) else value
    return cfg


def get_config():
    """Current configuration (defaults merged with the settings row)."""
    from lens_workflow.models import LensPricingSettings
    return merge(DEFAULTS, LensPricingSettings.load())


def dec(value):
    return Decimal(str(value))


def power_steps(lo, hi, step):
    lo, hi, step = dec(lo), dec(hi), dec(step)
    out = []
    v = lo
    while v <= hi:
        out.append(v.quantize(Decimal("0.01")))
        v += step
    return out
