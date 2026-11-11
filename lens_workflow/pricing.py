"""
Sell lenses from the imported price sheet.

The sheet price is the all-in pair price for one
(prescription type, lens type, color, depth, coating, index) at a sphere
and cylinder. It replaces the old stack of function + tint + index + color
+ blue-light coating. It does not include:

* prism ($27, still `Order.service.order_service.PRISM_SURCHARGE`) — the
  grid has no prism column
* Oleophobic / Hydrophobic (and any later paid coating that is not blue
  light) — the sheet's coating column is only N, Blue Light Filtering,
  Mirrored, or Polarized, and the last two are tint types, not these rows

Blue light filtering is a column on the sheet, so it is inside the cell.
Mirrored and polarized are that same column. They are not added again.

Lookup order is `lookup_price`: Premium, then Economic, and inside a tier
the Free Upgrade to 1.56 rule. "N", a blank color, and "Color Table" are
not prices. Cylinder above 6.00D is refused with the exact message
"Max CYL is 6.00D".

The live catalog calls the MR-8 mid-index 1.61. The sheet labels that lens
1.60. `CATALOG_INDEX_TO_SHEET` is the only alias; `lookup_price` itself
stays exact. 1.59 and 1.71 are not on the sheet and are not aliased.

Which index to offer is not decided here. The index step recommends from
the absolute steep meridian, not from this sheet's Recommended SE column.
Recommended SE is read only to spot the "Free Upgrade to 1.56" note.

A pair is priced from both eyes. Each eye must have a cell. The pair price
is the higher of the two (the sheet cell is already a pair price, matching
the old $4.95 economic plano). Cylinder sign follows the sheet: minus for
distance, bifocal, and progressive; plus for reading. Sphere is not
transposed.

When the table has no rows, catalog add-on prices are used and a warning
is logged, so a deploy before the import still checks out.
"""
import logging
import re
from dataclasses import dataclass, field, replace
from decimal import Decimal, ROUND_HALF_UP

from lens_workflow.models import (
    LensCoating,
    LensColorOption,
    LensIndexOption,
    LensPriceBlock,
)
from lens_workflow.price_table import (
    CENTS,
    is_unresolved_color,
    lookup_price,
)

logger = logging.getLogger(__name__)

MAX_CYL = Decimal("6.00")
MAX_CYL_MESSAGE = "Max CYL is 6.00D"

# The storefront's "1.61 Popular" / "1.61 Driving" rows are the MR-8 lens
# the sheet prices as 1.60. There is no 1.61 grid. 1.59 and 1.71 are absent
# and must not be pointed at another row.
CATALOG_INDEX_TO_SHEET = {
    Decimal("1.61"): Decimal("1.60"),
}

# Ladder the index step is allowed to show. 1.61 is the 1.60 rung.
# 1.59 (Safety / polycarbonate) and 1.71 (Elite) are not on it.
CANONICAL_INDEX_LADDER = (
    Decimal("1.50"),
    Decimal("1.56"),
    Decimal("1.60"),
    Decimal("1.67"),
    Decimal("1.74"),
)

# Material and Abbe number from the recommendation table (slides 33–35).
# 1.56 is only a budget neighbor, so it has no row there. The short
# material name is NK55. That sheet does not give NK-55 an Abbe number.
INDEX_PROFILES = {
    Decimal("1.50"): ("CR-39", Decimal("58.0")),
    Decimal("1.56"): ("NK55", None),
    Decimal("1.60"): ("MR-8", Decimal("41.0")),
    Decimal("1.67"): ("MR-7 / MR-10", Decimal("31.0")),
    Decimal("1.74"): ("MR-174", Decimal("32.0")),
}

# Inclusive upper bound of the absolute steep meridian, then the sheet index.
# 0.00–2.00 → 1.50, 2.25–4.00 → 1.60, 4.25–6.00 → 1.67, 6.25 and above → 1.74.
STEEP_MERIDIAN_BRACKETS = (
    (Decimal("2.00"), Decimal("1.50")),
    (Decimal("4.00"), Decimal("1.60")),
    (Decimal("6.00"), Decimal("1.67")),
    (None, Decimal("1.74")),
)

LENS_TYPE_TO_PRESCRIPTION = {
    "SVD": "Single Vision Distance",
    "READING": "Reading",
    "BIFOCAL": "Bifocal",
    "PROGRESSIVE": "Progressive",
    "NON_RX": "Single Vision Distance",
}

REASON_INDEX = "This index is not on the price sheet"
REASON_COLOR = "This color is not on the price sheet yet"
REASON_GRADIENT = "Gradient tints are not on the price sheet yet"
REASON_TINT = "Choose a tint type"
REASON_COLOR_CHOICE = "Choose a color"
REASON_INDEX_CHOICE = "Choose a lens index"
REASON_RX = "A prescription is required to price this lens"
REASON_NOT_OFFERED = "Not offered for this prescription"
REASON_BLUE_ON_TINT = "Blue light filtering is not on the price sheet for this tint"
EMPTY_TABLE_NOTE = "Price table is empty; using catalog add-on prices."

_BLUE = "BLUE_LIGHT_FILTERING"
_INCLUDED = {"ANTI_SCRATCH", "ANTI_GLARE", "UV_PROTECTION"}


class LensNotOffered(Exception):
    """The price table is loaded and this lens cannot be sold."""

    def __init__(self, message):
        super().__init__(message)
        self.message = message


class QuoteError(Exception):
    """The quote request itself is invalid (unknown id, bad combination)."""


def price_table_loaded():
    return LensPriceBlock.objects.exists()


def _money(value):
    if value is None:
        return None
    return f"{Decimal(value).quantize(CENTS):.2f}"


def _dec(value, default="0"):
    if value is None or value == "":
        value = default
    return Decimal(str(value)).quantize(CENTS, rounding=ROUND_HALF_UP)


def prism_requested(value):
    """True when the quote should add the prism surcharge.

    A boolean, a non-zero number, or any nested magnitude does. Direction
    strings alone do not.
    """
    if value is None or value is False:
        return False
    if value is True:
        return True
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes")
    if isinstance(value, (int, float, Decimal)):
        return Decimal(str(value)) != 0
    if isinstance(value, dict):
        return any(
            prism_requested(item) for key, item in value.items()
            if "direction" not in key)
    if isinstance(value, (list, tuple)):
        return any(prism_requested(item) for item in value)
    return False


def _log_empty_table():
    logger.warning(
        "Lens price table is empty; falling back to catalog add-on prices.")


def _prism_surcharge():
    from Order.service.order_service import PRISM_SURCHARGE
    return PRISM_SURCHARGE


def _has_prism_row(complete_set):
    from Order.service.order_service import has_prism
    return has_prism(complete_set)


@dataclass
class Eye:
    sph: Decimal = Decimal("0.00")
    cyl: Decimal = Decimal("0.00")
    add: Decimal = Decimal("0.00")
    pd: Decimal = Decimal("0.00")


@dataclass
class Extra:
    code: str
    label: str
    price: Decimal
    component: str


@dataclass
class EyeQuote:
    available: bool
    reason: str = None
    price: Decimal = None
    tier: str = None
    lens_index: Decimal = None
    free_upgrade: bool = False
    color: str = None
    depth: str = None
    coating: str = None
    prescription_type: str = None
    sheet_lens_type: str = None


@dataclass
class PricedOption:
    kind: str
    code: str
    label: str
    available: bool
    reason: str = None
    lens_price: Decimal = None
    tier: str = None
    lens_index: Decimal = None
    catalog_index: Decimal = None
    free_upgrade: bool = False
    prescription_type: str = None
    sheet_lens_type: str = None
    color: str = None
    depth: str = None
    coating: str = None
    option_id: int = None
    eyes: dict = None


@dataclass
class Quote:
    pricing_source: str
    blocked: bool = False
    block_reason: str = None
    note: str = None
    selection: PricedOption = None
    options: list = field(default_factory=list)
    extras: list = field(default_factory=list)
    prism: bool = False
    prism_price: Decimal = Decimal("0.00")
    total_lens_price: Decimal = None
    priced_eye: str = None
    od: Eye = None
    os: Eye = None

    @property
    def available(self):
        return (not self.blocked) and self.selection is not None and self.selection.available


@dataclass
class QuoteRequest:
    od: Eye
    os: Eye
    prism: bool = False
    lens_type_code: str = ""
    function_code: str = ""
    sun_type: str = ""
    color_name: str = ""
    density: str = ""
    index_value: Decimal = None
    coating_codes: tuple = ()
    lens_type: object = None
    function_path: object = None
    tint_type: object = None
    color_option: object = None
    index_option: object = None
    coatings: tuple = ()
    reader_strength: object = None
    prescription_missing: bool = False
    is_reader: bool = False
    is_non_rx: bool = False


def sheet_index_for(catalog_index):
    """Catalog index -> sheet index. 1.61 is the MR-8 lens priced as 1.60."""
    idx = _dec(catalog_index)
    return CATALOG_INDEX_TO_SHEET.get(idx, idx)


def canonical_index(value):
    """Catalog or sheet index collapsed onto the ladder. 1.61 and 1.60 match."""
    return sheet_index_for(value)


def recommended_canonical_index(power):
    """Sheet index for an absolute steep-meridian power (diopters)."""
    power = abs(_dec(power))
    for limit, index in STEEP_MERIDIAN_BRACKETS:
        if limit is None or power <= limit:
            return index
    return Decimal("1.74")


def neighbor_indexes(recommended):
    """Tiers to show with this recommendation.

    One step below and one step above, except 1.50, which also shows 1.60
    (the upgrade) as well as 1.56 (the budget option).
    """
    ladder = CANONICAL_INDEX_LADDER
    recommended = canonical_index(recommended)
    position = ladder.index(recommended)
    if recommended == Decimal("1.50"):
        return [ladder[0], ladder[1], ladder[2]]
    tiers = []
    if position > 0:
        tiers.append(ladder[position - 1])
    tiers.append(ladder[position])
    if position + 1 < len(ladder):
        tiers.append(ladder[position + 1])
    return tiers


def next_higher_index(index):
    """The next rung above `index`, or None at 1.74."""
    ladder = CANONICAL_INDEX_LADDER
    position = ladder.index(canonical_index(index))
    if position + 1 >= len(ladder):
        return None
    return ladder[position + 1]


def next_lower_index(index):
    """The next rung below `index`, or None at 1.50."""
    ladder = CANONICAL_INDEX_LADDER
    position = ladder.index(canonical_index(index))
    if position == 0:
        return None
    return ladder[position - 1]


def index_profile(catalog_index):
    """Return (material, abbe_number). abbe_number is a one-decimal string or None."""
    material, abbe = INDEX_PROFILES.get(canonical_index(catalog_index), ("", None))
    if abbe is None:
        return material, None
    return material, f"{abbe.quantize(Decimal('0.1'))}"


def available_index_labels(recommended):
    """Neighbor index strings, plus the catalog spelling 1.61 for the 1.60 rung."""
    labels = []
    for index in neighbor_indexes(recommended):
        labels.append(f"{index.quantize(Decimal('0.01'))}")
        if index == Decimal("1.60"):
            labels.append("1.61")
    return labels


def _norm_color(text):
    return (text or "").lower().replace("grey", "gray")


def _color_group(function_code, color_name):
    if function_code in ("CLEAR", _BLUE, ""):
        return "N"
    low = _norm_color(color_name)
    if not low.strip():
        return None
    if "gray" in low or "brown" in low:
        return "Gray, Brown"
    if any(word in low for word in ("pink", "purple", "blue")):
        return "Pink, Purple, Blue"
    return None


def _depth_tokens(depth):
    raw = (depth or "N").strip()
    if raw in ("", "N"):
        return {"N"}
    tokens = set()
    for part in raw.replace(";", ",").split(","):
        part = part.strip().lower().replace(" ", "")
        if part in ("0.8", "0.80", "80%", "80"):
            tokens.add("80%")
        elif part in ("0.5", "0.50", "50%", "50"):
            tokens.add("50%")
        elif part in ("0.3", "0.30", "30%", "30"):
            tokens.add("30%")
        elif part.endswith("%"):
            tokens.add(part)
        elif part:
            tokens.add(part)
    return tokens or {"N"}


def _depth_token(function_code, sun_type, color_name, density):
    if function_code != "SUN":
        return "N"
    if sun_type in ("POLARIZED", "MIRRORED"):
        return "N"
    if sun_type == "GRADIENT":
        return None
    if sun_type == "SOLID":
        match = re.search(r"(\d+(?:\.\d+)?)\s*%", f"{color_name or ''} {density or ''}")
        if not match:
            return None
        return f"{int(Decimal(match.group(1)))}%"
    return "N"


def _sheet_coating(function_code, sun_type, coating_codes):
    if sun_type == "POLARIZED":
        base = "Polarized"
    elif sun_type == "MIRRORED":
        base = "Mirrored"
    else:
        base = "N"
    blue = function_code == _BLUE or _BLUE in coating_codes
    if blue and base != "N":
        return None
    if blue:
        return "Blue Light Filtering"
    return base


def _sheet_lens(function_code):
    if function_code == "PHOTOCHROMIC":
        return "Photochromic"
    if function_code == "SUN":
        return "Sun/Tint"
    return "Clear"


def _color_matches(block_color, group):
    if is_unresolved_color(block_color) or group is None:
        return False
    if group == "N":
        return (block_color or "").strip() == "N"
    return _norm_color(block_color).replace(" ", "") == _norm_color(group).replace(" ", "")


def _depth_matches(block_depth, wanted):
    if wanted is None:
        return False
    return wanted in _depth_tokens(block_depth)


def _align_cylinder(block, cylinder):
    """Match the sign the sheet uses for this block. Magnitude is unchanged
    and sphere is not transposed — these grids are priced on cylinder power."""
    magnitude = abs(_dec(cylinder))
    axes = [Decimal(str(value)) for value in (block.cylinder_axis or [])]
    if any(axis < 0 for axis in axes) and not any(axis > 0 for axis in axes):
        return -magnitude if magnitude else Decimal("0.00")
    if any(axis > 0 for axis in axes) and not any(axis < 0 for axis in axes):
        return magnitude
    return _dec(cylinder)


def _needs_color(req):
    if req.tint_type is not None and req.tint_type.color_required:
        return True
    if req.function_path is not None and req.function_path.color_required and not req.sun_type:
        return True
    if req.function_code == "PHOTOCHROMIC":
        return True
    return req.function_code == "SUN" and req.sun_type in (
        "SOLID", "GRADIENT", "MIRRORED", "POLARIZED")


def _legacy_parts(req):
    total = Decimal("0.00")
    if req.function_path is not None:
        total += req.function_path.extra_price or 0
    if req.tint_type is not None:
        total += req.tint_type.extra_price or 0
    if req.index_option is not None:
        total += req.index_option.price or 0
    elif req.index_value is not None and req.lens_type is not None:
        row = LensIndexOption.objects.filter(
            lens_type=req.lens_type, index_value=req.index_value, is_active=True).first()
        if row is not None:
            total += row.price or 0
    if req.color_option is not None:
        total += req.color_option.extra_price or 0
    for coating in req.coatings:
        total += coating.price or 0
    if req.reader_strength is not None:
        total += req.reader_strength.price or 0
    return _dec(total)


def _extras(req, *, sheet):
    """Paid coatings the sheet does not already include."""
    rows = []
    for coating in req.coatings:
        if coating.is_included or coating.code in _INCLUDED:
            continue
        if sheet and coating.code == _BLUE:
            continue
        rows.append(Extra(
            code=coating.code,
            label=coating.label,
            price=_dec(coating.price or 0),
            component=f"coating_{coating.id}",
        ))
    return rows


def _over_max_cyl(req):
    return abs(req.od.cyl) > MAX_CYL or abs(req.os.cyl) > MAX_CYL


def _load_blocks(prescription_type, sheet_lens):
    return list(LensPriceBlock.objects.filter(
        prescription_type=prescription_type, lens_type=sheet_lens))


def _match_block(blocks, tier, coating, index, color_group, depth_token):
    found = []
    for block in blocks:
        if block.tier != tier or block.coating != coating:
            continue
        if block.lens_index != index:
            continue
        if not _color_matches(block.color, color_group):
            continue
        if not _depth_matches(block.depth, depth_token):
            continue
        found.append(block)
    if not found:
        return None
    found.sort(key=lambda block: (len(_depth_tokens(block.depth)), block.position, block.id))
    return found[0]


def _unresolved_only(blocks, coating, index):
    rows = [b for b in blocks if b.coating == coating and b.lens_index == index]
    if not rows:
        return False
    return all(is_unresolved_color(b.color) for b in rows)


def _any_index_blocks(blocks, index):
    return any(b.lens_index == index for b in blocks)


def _price_eye(blocks, prescription_type, sheet_lens, color_group, depth_token,
               coating, index, sphere, cylinder):
    """Premium first, then Economic, each through `lookup_price` so a tier
    whose depth text differs (``30%, 50%`` vs ``0.8``) is still tried."""
    seen = []
    for tier in ("premium", "economic"):
        block = _match_block(blocks, tier, coating, index, color_group, depth_token)
        if block is None:
            continue
        key = (block.color, block.depth, block.coating, block.lens_index)
        if key in seen:
            continue
        seen.append(key)
        hit = lookup_price(
            prescription_type, sheet_lens, block.color, block.depth, block.coating,
            index, _dec(sphere), _align_cylinder(block, cylinder))
        if hit is not None:
            return EyeQuote(
                available=True, price=hit.price, tier=hit.tier,
                lens_index=hit.lens_index, free_upgrade=hit.free_upgrade,
                color=block.color, depth=block.depth, coating=block.coating,
                prescription_type=prescription_type, sheet_lens_type=sheet_lens)
    return None


def _pair(blocks, prescription_type, sheet_lens, color_group, depth_token,
          coating, index, od, os):
    eyes = {}
    for name, eye in (("od", od), ("os", os)):
        hit = _price_eye(
            blocks, prescription_type, sheet_lens, color_group, depth_token,
            coating, index, eye.sph, eye.cyl)
        if hit is None:
            eyes[name] = EyeQuote(available=False, reason=REASON_NOT_OFFERED)
        else:
            eyes[name] = hit
    if not all(item.available for item in eyes.values()):
        return None, eyes
    winner_name = max(
        eyes,
        key=lambda name: (eyes[name].price, abs(od.sph if name == "od" else os.sph)),
    )
    return winner_name, eyes


def _option_from_eyes(kind, code, label, option_id, catalog_index, winner, eyes, reason):
    hit = eyes.get(winner) if winner else None
    if hit is None or not hit.available:
        return PricedOption(
            kind=kind, code=code, label=label, option_id=option_id,
            available=False, reason=reason or REASON_NOT_OFFERED,
            catalog_index=catalog_index, eyes=_eyes_dict(eyes))
    return PricedOption(
        kind=kind, code=code, label=label, option_id=option_id, available=True,
        lens_price=hit.price, tier=hit.tier, lens_index=hit.lens_index,
        catalog_index=catalog_index, free_upgrade=hit.free_upgrade,
        prescription_type=hit.prescription_type, sheet_lens_type=hit.sheet_lens_type,
        color=hit.color, depth=hit.depth, coating=hit.coating,
        eyes=_eyes_dict(eyes))


def _eyes_dict(eyes):
    out = {}
    for name, hit in (eyes or {}).items():
        out[name] = {
            "available": hit.available,
            "reason": hit.reason,
            "price": _money(hit.price),
            "tier": hit.tier,
            "lens_index": _money(hit.lens_index) if hit.lens_index is not None else None,
            "free_upgrade": hit.free_upgrade,
        }
    return out


def _finish(quote, req, lens_price, *, sheet):
    # Legacy `lens_price` already includes every catalog add-on. The sheet
    # cell does not include prism or coatings the grid has no column for.
    extras = _extras(req, sheet=True) if sheet else []
    prism_price = _prism_surcharge() if req.prism else Decimal("0.00")
    extra_total = sum((row.price for row in extras), Decimal("0.00"))
    if lens_price is None:
        quote.total_lens_price = None
    else:
        quote.total_lens_price = _dec(lens_price + extra_total + prism_price)
    quote.extras = extras
    quote.prism = bool(req.prism)
    quote.prism_price = prism_price
    if quote.od is None:
        quote.od = req.od
    if quote.os is None:
        quote.os = req.os
    return quote


def _blocked(req):
    quote = Quote(
        pricing_source="price_table" if price_table_loaded() else "legacy",
        blocked=True, block_reason=MAX_CYL_MESSAGE, od=req.od, os=req.os)
    return quote


def _legacy_quote(req, *, empty_table):
    if empty_table:
        _log_empty_table()
    configured = bool(
        req.is_reader or req.lens_type_code == "READER" or req.function_code
        or req.index_value is not None or req.reader_strength is not None)
    lens_price = _legacy_parts(req) if configured else None
    selection = None
    if lens_price is not None and (req.index_value is not None or req.is_reader or req.reader_strength is not None or req.function_code):
        selection = PricedOption(
            kind="index",
            code=str(req.index_value if req.index_value is not None else ""),
            label=(req.index_option.option_label if req.index_option is not None
                   else (req.reader_strength.label if req.reader_strength is not None else "Lens")),
            available=True,
            lens_price=lens_price,
            catalog_index=req.index_value,
            option_id=req.index_option.id if req.index_option is not None else None,
        )
    quote = Quote(
        pricing_source="legacy",
        note=EMPTY_TABLE_NOTE if empty_table else None,
        selection=selection)
    options = []
    if req.lens_type is not None and not req.is_reader:
        for row in LensIndexOption.objects.filter(lens_type=req.lens_type, is_active=True).order_by("sort_order", "id"):
            priced = _legacy_parts(QuoteRequest(
                od=req.od, os=req.os, prism=False,
                function_path=req.function_path, tint_type=req.tint_type,
                color_option=req.color_option, index_option=row, index_value=row.index_value,
                coatings=req.coatings, lens_type=req.lens_type))
            options.append(PricedOption(
                kind="index", code=str(row.index_value), label=row.option_label,
                option_id=row.id, available=True, lens_price=priced,
                catalog_index=row.index_value))
    quote.options = options
    return _finish(quote, req, selection.lens_price if selection else None, sheet=False)


def _prepare_sheet_key(req):
    """Return (error_reason, prescription_type, sheet_lens, color_group, depth, coating)
    or an error reason and Nones."""
    if req.function_code == "SUN" and not req.sun_type:
        return REASON_TINT, None, None, None, None, None
    if req.sun_type == "GRADIENT":
        return REASON_GRADIENT, None, None, None, None, None
    if _needs_color(req) and not (req.color_name or "").strip():
        return REASON_COLOR_CHOICE, None, None, None, None, None
    coating = _sheet_coating(req.function_code, req.sun_type, req.coating_codes)
    if coating is None:
        return REASON_BLUE_ON_TINT, None, None, None, None, None
    group = _color_group(req.function_code, req.color_name)
    if group is None:
        return REASON_COLOR, None, None, None, None, None
    depth = _depth_token(req.function_code, req.sun_type, req.color_name, req.density)
    if depth is None:
        return REASON_COLOR, None, None, None, None, None
    prescription_type = LENS_TYPE_TO_PRESCRIPTION.get(req.lens_type_code)
    if prescription_type is None:
        raise QuoteError(f"Unknown lens type '{req.lens_type_code}'.")
    return None, prescription_type, _sheet_lens(req.function_code), group, depth, coating


def _price_index(blocks, prescription_type, sheet_lens, color_group, depth, coating,
                 catalog_index, od, os):
    index = sheet_index_for(catalog_index)
    if not _any_index_blocks(blocks, index):
        return REASON_INDEX, None, {}
    if _unresolved_only(blocks, coating, index):
        return REASON_COLOR, None, {}
    # Usable blocks exist for the index, but none for this color/depth.
    if _match_block(blocks, "premium", coating, index, color_group, depth) is None \
            and _match_block(blocks, "economic", coating, index, color_group, depth) is None:
        color_blocks = [b for b in blocks if b.coating == coating and b.lens_index == index
                        and not is_unresolved_color(b.color)]
        if not color_blocks:
            return REASON_COLOR, None, {}
        return REASON_NOT_OFFERED, None, {}
    winner, eyes = _pair(
        blocks, prescription_type, sheet_lens, color_group, depth, coating, index, od, os)
    if winner is None:
        return REASON_NOT_OFFERED, None, eyes
    return None, winner, eyes


def _index_menu(req):
    if req.lens_type is not None:
        rows = list(LensIndexOption.objects.filter(
            lens_type=req.lens_type, is_active=True).order_by("sort_order", "id"))
        if rows:
            return [(row.index_value, row.option_label, row.id) for row in rows]
    return []


def _sheet_quote(req, *, include_options, require_index):
    if req.prescription_missing and not req.is_non_rx:
        selection = PricedOption(
            kind="index", code="", label="", available=False, reason=REASON_RX,
            catalog_index=req.index_value)
        quote = Quote(pricing_source="price_table", selection=selection, od=req.od, os=req.os)
        return _finish(quote, req, None, sheet=True)

    reason, prescription_type, sheet_lens, color_group, depth, coating = _prepare_sheet_key(req)
    if reason == REASON_COLOR_CHOICE:
        quote = Quote(pricing_source="price_table", od=req.od, os=req.os)
        quote.options = _color_options(req)
        quote.selection = PricedOption(
            kind="color", code="", label="", available=False, reason=REASON_COLOR_CHOICE)
        return _finish(quote, req, None, sheet=True)
    if reason is not None:
        selection = PricedOption(
            kind="index",
            code="" if req.index_value is None else str(req.index_value),
            label=req.index_option.option_label if req.index_option is not None else "",
            option_id=req.index_option.id if req.index_option is not None else None,
            available=False, reason=reason, catalog_index=req.index_value)
        quote = Quote(pricing_source="price_table", selection=selection, od=req.od, os=req.os)
        return _finish(quote, req, None, sheet=True)

    if req.is_non_rx:
        zero = Eye()
        od, os = zero, zero
    else:
        od, os = req.od, req.os

    blocks = _load_blocks(prescription_type, sheet_lens)
    options = []
    if include_options:
        menu = _index_menu(req)
        if not menu:
            indexes = sorted({
                b.lens_index for b in blocks
                if b.coating == coating and not is_unresolved_color(b.color)
                and _color_matches(b.color, color_group) and _depth_matches(b.depth, depth)
            })
            menu = [(idx, f"Index {idx}", None) for idx in indexes]
        for catalog_index, label, option_id in menu:
            err, winner, eyes = _price_index(
                blocks, prescription_type, sheet_lens, color_group, depth, coating,
                catalog_index, od, os)
            options.append(_option_from_eyes(
                "index", str(catalog_index), label, option_id, _dec(catalog_index),
                winner, eyes, err))

    selection = None
    winner_name = None
    if req.index_value is None:
        if require_index:
            selection = PricedOption(
                kind="index", code="", label="", available=False,
                reason=REASON_INDEX_CHOICE)
    else:
        err, winner_name, eyes = _price_index(
            blocks, prescription_type, sheet_lens, color_group, depth, coating,
            req.index_value, od, os)
        label = req.index_option.option_label if req.index_option is not None else f"Index {req.index_value}"
        selection = _option_from_eyes(
            "index", str(req.index_value), label,
            req.index_option.id if req.index_option is not None else None,
            _dec(req.index_value), winner_name, eyes, err)

    quote = Quote(
        pricing_source="price_table", selection=selection, options=options,
        priced_eye=winner_name, od=od, os=os)
    lens_price = selection.lens_price if selection is not None and selection.available else None
    return _finish(quote, req, lens_price, sheet=True)


def _color_options(req):
    """Colors for a photochromic / sun step, each priced when an index was sent."""
    path = req.tint_type or req.function_path
    colors = []
    if path is not None:
        colors = list(LensColorOption.objects.filter(
            function_path=path, is_active=True).order_by("sort_order", "id"))
    if not colors:
        return []
    options = []
    for color in colors:
        clone = replace(req, color_name=color.color_name, color_option=color)
        priced = _sheet_quote(clone, include_options=False, require_index=False)
        selection = priced.selection
        options.append(PricedOption(
            kind="color", code=color.color_name, label=color.color_name, option_id=color.id,
            available=bool(selection and selection.available),
            reason=None if selection and selection.available else (
                selection.reason if selection else REASON_NOT_OFFERED),
            lens_price=selection.lens_price if selection and selection.available else None,
            tier=selection.tier if selection else None,
            lens_index=selection.lens_index if selection else None,
            catalog_index=req.index_value,
            free_upgrade=selection.free_upgrade if selection else False,
            prescription_type=selection.prescription_type if selection else None,
            sheet_lens_type=selection.sheet_lens_type if selection else None,
            color=selection.color if selection else None,
            depth=selection.depth if selection else None,
            coating=selection.coating if selection else None,
        ))
    return options


def quote(req, *, include_options=True, require_index=False):
    """Price `req`. Does not raise `LensNotOffered` — callers that charge
    money inspect `available` / `blocked` and refuse themselves."""
    if req.is_reader or req.lens_type_code == "READER":
        return _legacy_quote(req, empty_table=False)
    if not req.function_code and req.index_value is None and not require_index:
        raise QuoteError("function_code or function_path_id is required.")
    if (not req.is_non_rx) and (not req.is_reader) and _over_max_cyl(req):
        blocked = _blocked(req)
        blocked.od = req.od
        blocked.os = req.os
        return blocked
    if not price_table_loaded():
        return _legacy_quote(req, empty_table=True)
    if not req.function_code:
        raise QuoteError("function_code or function_path_id is required.")
    return _sheet_quote(req, include_options=include_options, require_index=require_index)


def catalog_index_available(req):
    """True when `req.index_value` can be sold for this prescription.

    An empty price table counts as available: checkout would use the catalog
    add-on price. Otherwise both eyes need a real sheet cell. "N", a blank
    color, and "Color Table" are not prices. Free Upgrade to 1.56 counts as
    a price for 1.50, and catalog 1.61 is priced from the 1.60 cell.

    This does not apply the CYL > 6.00 refusal. `quote` still blocks that
    prescription with "Max CYL is 6.00D". A cylinder the sheet has no column
    for simply comes back unavailable.
    """
    if req.index_value is None:
        return False
    if not price_table_loaded():
        return True
    try:
        result = _sheet_quote(req, include_options=False, require_index=True)
    except QuoteError:
        return False
    return bool(result.available)


def _coatings_of(complete_set):
    if not complete_set.pk:
        return ()
    return tuple(complete_set.coatings.all())


def quote_request_from_complete_set(complete_set):
    lens_type = complete_set.lens_type
    function_path = complete_set.function_path
    tint = complete_set.tint_type
    code = lens_type.code if lens_type is not None else ""
    is_reader = bool(lens_type and (lens_type.is_reader or code == "READER")) or (
        complete_set.reader_strength_id and lens_type is None)
    is_non_rx = bool(lens_type and (code == "NON_RX" or not lens_type.is_prescription_required and not is_reader))
    # Non-prescription is the only non-reader type with is_prescription_required False.
    if lens_type is not None and not lens_type.is_prescription_required and not is_reader:
        is_non_rx = True
    function_code = function_path.function_code if function_path is not None else ""
    sun_type = ""
    if tint is not None and tint.sun_type:
        sun_type = tint.sun_type
    elif function_path is not None and function_path.sun_type:
        sun_type = function_path.sun_type
    color_name = complete_set.color_option.color_name if complete_set.color_option_id else ""
    index_value = complete_set.index_option.index_value if complete_set.index_option_id else None
    coatings = _coatings_of(complete_set)
    rx = complete_set.prescription if complete_set.prescription_id else None
    if is_non_rx or rx is None:
        od, os = Eye(), Eye()
    else:
        od = Eye(_dec(rx.sphere_r), _dec(rx.cylinder_r), _dec(rx.add_r), _dec(rx.pd_r))
        os = Eye(_dec(rx.sphere_l), _dec(rx.cylinder_l), _dec(rx.add_l), _dec(rx.pd_l))
    return QuoteRequest(
        od=od, os=os, prism=_has_prism_row(complete_set),
        lens_type_code=code, function_code=function_code, sun_type=sun_type,
        color_name=color_name, density=complete_set.density or "",
        index_value=index_value, coating_codes=tuple(c.code for c in coatings),
        lens_type=lens_type, function_path=function_path, tint_type=tint,
        color_option=complete_set.color_option, index_option=complete_set.index_option,
        coatings=coatings, reader_strength=complete_set.reader_strength,
        prescription_missing=rx is None and not is_non_rx and not is_reader,
        is_reader=is_reader, is_non_rx=is_non_rx)


def quote_for_complete_set(complete_set):
    if complete_set.lens_type_id is None and complete_set.function_path_id is None \
            and complete_set.index_option_id is None and complete_set.reader_strength_id is None:
        return Quote(pricing_source="legacy", total_lens_price=Decimal("0.00"),
                     od=Eye(), os=Eye())
    req = quote_request_from_complete_set(complete_set)
    return quote(req, include_options=False, require_index=not req.is_reader)


def lens_total_for_complete_set(complete_set):
    """Lens portion of a CompleteSet (no frame). Raises `LensNotOffered`
    when the sheet is loaded and this configuration cannot be made."""
    if complete_set.lens_type_id is None and complete_set.function_path_id is None \
            and complete_set.index_option_id is None and complete_set.reader_strength_id is None:
        return Decimal("0.00")
    try:
        result = quote_for_complete_set(complete_set)
    except QuoteError as exc:
        raise LensNotOffered(str(exc)) from exc
    if result.pricing_source == "legacy":
        return result.total_lens_price or Decimal("0.00")
    if result.blocked or not result.available:
        message = result.block_reason or (
            result.selection.reason if result.selection is not None else REASON_NOT_OFFERED)
        raise LensNotOffered(message or REASON_NOT_OFFERED)
    return result.total_lens_price


def line_items_for_complete_set(complete_set):
    """Sheet line items, or None when the caller should use the legacy stack.

    An unavailable sheet lens returns one zero-dollar row so a cart GET does
    not 500; checkout still refuses to charge it.
    """
    if complete_set.lens_type_id is None and complete_set.function_path_id is None \
            and complete_set.index_option_id is None:
        return None
    if complete_set.lens_type_id and (
            complete_set.lens_type.is_reader or complete_set.lens_type.code == "READER"):
        return None
    try:
        result = quote_for_complete_set(complete_set)
    except QuoteError as exc:
        return [{
            "component": "lens",
            "label": str(exc),
            "price": 0.0,
            "unavailable": True,
        }]
    if result.pricing_source == "legacy":
        return None
    if result.blocked or not result.available:
        message = result.block_reason or (
            result.selection.reason if result.selection is not None else REASON_NOT_OFFERED)
        return [{
            "component": "lens",
            "label": message,
            "price": 0.0,
            "unavailable": True,
        }]
    selection = result.selection
    label_bits = [selection.sheet_lens_type or "Lens", f"index {selection.lens_index}"]
    if selection.color and selection.color != "N":
        label_bits.append(selection.color)
    if selection.coating and selection.coating != "N":
        label_bits.append(selection.coating)
    label_bits.append(selection.tier or "")
    if selection.free_upgrade:
        label_bits.append(f"free upgrade from {selection.catalog_index}")
    items = [{
        "component": "lens",
        "label": " / ".join(bit for bit in label_bits if bit),
        "price": float(selection.lens_price),
        "tier": selection.tier,
        "lens_index": _money(selection.lens_index),
        "catalog_index": _money(selection.catalog_index),
        "free_upgrade": selection.free_upgrade,
    }]
    for extra in result.extras:
        items.append({
            "component": extra.component,
            "label": extra.label,
            "price": float(extra.price),
        })
    if result.prism:
        items.append({
            "component": "prism",
            "label": "Prism",
            "price": float(result.prism_price),
        })
    return items


def _option_dict(option):
    if option is None:
        return None
    return {
        "kind": option.kind,
        "id": option.option_id,
        "code": option.code,
        "label": option.label,
        "available": option.available,
        "reason": option.reason,
        "lens_price": _money(option.lens_price),
        "tier": option.tier,
        "lens_index": _money(option.lens_index) if option.lens_index is not None else None,
        "catalog_index": _money(option.catalog_index) if option.catalog_index is not None else None,
        "free_upgrade": option.free_upgrade,
        "prescription_type": option.prescription_type,
        "lens_type": option.sheet_lens_type,
        "color": option.color,
        "depth": option.depth,
        "coating": option.coating,
        "eyes": option.eyes,
    }


def quote_to_dict(result):
    return {
        "pricing_source": result.pricing_source,
        "blocked": result.blocked,
        "block_reason": result.block_reason,
        "note": result.note,
        "priced_eye": result.priced_eye,
        "prescription": {
            "od": {
                "sph": _money(result.od.sph) if result.od else None,
                "cyl": _money(result.od.cyl) if result.od else None,
                "add": _money(result.od.add) if result.od else None,
                "pd": _money(result.od.pd) if result.od else None,
            },
            "os": {
                "sph": _money(result.os.sph) if result.os else None,
                "cyl": _money(result.os.cyl) if result.os else None,
                "add": _money(result.os.add) if result.os else None,
                "pd": _money(result.os.pd) if result.os else None,
            },
        },
        "selection": _option_dict(result.selection),
        "options": [_option_dict(option) for option in result.options],
        "extras": [
            {"code": extra.code, "label": extra.label, "price": _money(extra.price)}
            for extra in result.extras
        ],
        "prism": {"applied": result.prism, "price": _money(result.prism_price)},
        "total_lens_price": _money(result.total_lens_price),
    }
