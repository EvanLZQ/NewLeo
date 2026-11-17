"""Lens pricing rules (round 3 spec, impl of /round3/REPORT3.md §1).

Pure functions over a `Catalog` (parsed blocks of one price version) and a
config dict (config.get_config()). No database access, so every rule is
unit-tested directly.

Glossary
    Rx'        prescription after minus-cylinder transposition; used ONLY to
               classify and price (orders keep the original Rx, R2-17)
    rx_type    which table an eye uses: SV_NEAR / SV_FAR / BIFOCAL / PROGRESSIVE
    product    (line, rx_type, lens_type, colour group, depths, coating)
    m          steepest meridian = max(|S'|, |S' + C'|)
"""
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP

from . import config as C
from .sheet import SubRow

CENTS = Decimal("0.01")
Q = lambda v: Decimal(str(v)).quantize(CENTS, rounding=ROUND_HALF_UP)   # noqa: E731

SV = "SINGLE_VISION"
BIFOCAL = "BIFOCAL"
PROGRESSIVE = "PROGRESSIVE"
READERS = "READERS"
NON_RX = "NON_RX"
CATEGORIES = (SV, BIFOCAL, PROGRESSIVE, READERS, NON_RX)

REASON_NO_RX = "This prescription can't be ordered online right now. Please contact us and we'll help."
REASON_MAX_CYL = "Max CYL is {max_cyl}D"


class SelectionError(ValueError):
    """The request itself is invalid (unknown code, missing step)."""


# ── catalog ──────────────────────────────────────────────────────────────────

@dataclass
class Block:
    id: object
    line: str
    sheet: str
    source_row: int
    position: int
    rx_type: str
    lens_type: str
    color_group: str
    colors: list
    is_generic_color: bool
    depths: list
    coating: str
    lens_index: Decimal
    material: str
    rows: list            # [SubRow]
    grid: dict            # (|S|, |C|) -> Decimal

    def price(self, s, c):
        return self.grid.get((Q(s), Q(c)))

    def limitation_ok(self, s, c):
        return any(r.limitation_ok(s, c) for r in self.rows)

    def label_for(self, m, s, c):
        """Label of the first sub-row whose steep range holds m and whose
        Limitation holds (Q13=A: the range only picks the label)."""
        for r in self.rows:
            if r.steep_min <= m <= r.steep_max and r.limitation_ok(s, c):
                return r.label, r.upgrade_to
        return None, None

    def steep_covers(self, m):
        return any(r.steep_min <= m <= r.steep_max for r in self.rows)

    def ref(self):
        return {"block_id": self.id, "sheet": self.sheet, "row": self.source_row,
                "index": str(self.lens_index), "line": self.line}


def block_from_parsed(pb, id=None):
    return Block(id=id, line=pb.line, sheet=pb.sheet, source_row=pb.source_row, position=pb.position,
                 rx_type=pb.rx_type, lens_type=pb.lens_type, color_group=pb.color_group,
                 colors=list(pb.colors), is_generic_color=pb.is_generic_color, depths=list(pb.depths),
                 coating=pb.coating, lens_index=pb.lens_index, material=pb.material,
                 rows=list(pb.rows), grid=dict(pb.grid))


def block_from_row(row):
    grid = {}
    for k, v in (row.grid or {}).items():
        s, c = k.split("|")
        grid[(Q(s), Q(c))] = Decimal(v)
    return Block(id=row.id, line=row.line.code, sheet=row.sheet, source_row=row.source_row,
                 position=row.position, rx_type=row.rx_type, lens_type=row.lens_type,
                 color_group=row.color_group, colors=list(row.colors or []),
                 is_generic_color=row.is_generic_color, depths=list(row.depths or []),
                 coating=row.coating, lens_index=Decimal(row.lens_index), material=row.material,
                 rows=[SubRow.from_dict(d) for d in (row.rows or [])], grid=grid)


@dataclass
class Line:
    code: str
    display_name: str
    sort_order: int = 0
    description: str = ""


class Catalog:
    """All blocks of one price version, indexed for lookup."""

    def __init__(self, blocks, lines, version_id=None, version_label=""):
        self.version_id = version_id
        self.version_label = version_label
        self.lines = sorted(lines, key=lambda x: (x.sort_order, x.code))
        self.line_by_code = {x.code: x for x in self.lines}
        self.blocks = [b for b in blocks if b.line in self.line_by_code]
        self._by = defaultdict(list)
        for b in self.blocks:
            self._by[(b.line, b.rx_type, b.lens_type, b.coating)].append(b)

    def candidates(self, line, rx_type, lens_type, coating):
        return self._by.get((line, rx_type, lens_type, coating), [])


# ── prescription ─────────────────────────────────────────────────────────────

@dataclass
class EyeRx:
    sph: Decimal = Decimal("0")
    cyl: Decimal = Decimal("0")
    axis: int = None


@dataclass
class PricingEye:
    sph: Decimal          # S' (minus-cyl form)
    cyl: Decimal          # C' (<= 0)
    axis: int
    s: Decimal            # |S'|
    c: Decimal            # |C'|
    m: Decimal            # steepest meridian
    rx_type: str

    def as_dict(self):
        return {"sph": str(self.sph), "cyl": str(self.cyl), "axis": self.axis,
                "steep_meridian": str(self.m), "table": self.rx_type}


def transpose(eye):
    """Plus-cylinder → minus-cylinder (R2-17). S'=S+C, C'=-C, axis ±90."""
    s, c = Q(eye.sph or 0), Q(eye.cyl or 0)
    axis = eye.axis
    if c > 0:
        s, c = Q(s + c), Q(-c)
        if axis is not None:
            axis = ((int(axis) + 90 - 1) % 180) + 1
    return s, c, axis


def pricing_eye(eye, category):
    s, c, axis = transpose(eye)
    if category in (SV, NON_RX, READERS):
        # S' > 0 → farsighted table; S' <= 0 (incl. plano with cylinder) →
        # nearsighted. Mixed astigmatism (S'>0, S'+C'<0) → farsighted (Q1=A).
        rx_type = "SV_FAR" if s > 0 else "SV_NEAR"
    elif category == BIFOCAL:
        rx_type = "BIFOCAL"
    elif category == PROGRESSIVE:
        rx_type = "PROGRESSIVE"
    else:
        raise SelectionError(f"unknown category {category}")
    m = max(abs(s), abs(s + c))
    return PricingEye(sph=s, cyl=c, axis=axis, s=abs(s), c=abs(c), m=Q(m), rx_type=rx_type)


# ── selection → blocks ──────────────────────────────────────────────────────

@dataclass(frozen=True)
class Selection:
    lens_type: str              # CLEAR / PHOTOCHROMIC / SUN
    tint: str = ""              # SOLID / GRADIENT / POLARIZED / MIRRORED (SUN only)
    color: str = ""             # colour code (PHOTOCHROMIC, SUN)
    depth: int = None           # 30 / 50 / 80 (SOLID, GRADIENT)
    coating: str = "N"          # N / BLUE (POLARIZED / MIRRORED imply their own)

    @property
    def sheet_coating(self):
        if self.tint in ("POLARIZED", "MIRRORED"):
            return self.tint
        return self.coating or "N"

    def as_dict(self):
        return {"lens_type": self.lens_type, "tint": self.tint or None, "color": self.color or None,
                "depth": self.depth, "coating": self.coating or "N"}


def validate_selection(sel):
    if sel.lens_type not in ("CLEAR", "PHOTOCHROMIC", "SUN"):
        raise SelectionError("lens_type must be CLEAR, PHOTOCHROMIC or SUN")
    if sel.lens_type == "SUN":
        if sel.tint not in ("SOLID", "GRADIENT", "POLARIZED", "MIRRORED"):
            raise SelectionError("tint must be SOLID, GRADIENT, POLARIZED or MIRRORED for SUN")
        if not sel.color:
            raise SelectionError("color is required")
        if sel.tint in ("SOLID", "GRADIENT") and sel.depth is None:
            raise SelectionError("depth is required for solid and gradient tints")
        if sel.tint in ("POLARIZED", "MIRRORED") and (sel.coating or "N") != "N":
            raise SelectionError("polarized / mirrored lenses take no extra coating")
    elif sel.lens_type == "PHOTOCHROMIC":
        if not sel.color:
            raise SelectionError("color is required")
    if (sel.coating or "N") not in ("N", "BLUE"):
        raise SelectionError("coating must be N or BLUE")


def product_blocks(catalog, cfg, line, rx_type, sel):
    """Blocks (one per index) that price `sel` for one eye table.

    Colour priority (R2-3(b), 8(c)): if any non-generic block of the product
    lists the colour at this depth, only those blocks are used; the generic
    "Sun & Tint Colors" blocks are a fallback. Gradient at a depth in
    gradient_ignore_dedicated_depths skips the dedicated blocks (boss Q3
    default: 80% gray/brown gradient = general price)."""
    found = []
    for b in catalog.candidates(line, rx_type, sel.lens_type, sel.sheet_coating):
        if sel.lens_type == "CLEAR":
            if b.colors:
                continue
        elif sel.color not in b.colors:
            continue
        if sel.lens_type == "SUN" and sel.tint in ("SOLID", "GRADIENT"):
            if sel.depth not in b.depths:
                continue
        elif b.depths:
            continue
        found.append(b)
    if sel.lens_type == "SUN" and sel.tint == "GRADIENT":
        if not cfg.get("gradient_enabled", True):
            return {}
        if sel.depth in (cfg.get("gradient_ignore_dedicated_depths") or []):
            generic = [b for b in found if b.is_generic_color]
            if generic:
                found = generic
    dedicated = [b for b in found if not b.is_generic_color]
    if dedicated:
        found = dedicated
    out = {}
    for b in sorted(found, key=lambda x: (x.position,)):
        out.setdefault(b.lens_index, b)
    return out


# ── one eye ──────────────────────────────────────────────────────────────────

@dataclass
class EyeOption:
    index: Decimal
    price: Decimal
    label: str              # RECOMMENDED / AVAILABLE / FREE_UPGRADE / None
    upgrade_to: Decimal
    block: Block


def eye_options(blocks, eye, cfg):
    """index → EyeOption for every index this eye can buy (§1.2.1)."""
    enforce = bool(cfg.get("enforce_limitation", True))
    out = {}
    for idx, b in blocks.items():
        p = b.price(eye.s, eye.c)
        if p is None:
            continue
        if enforce and not b.limitation_ok(eye.s, eye.c):
            continue
        label, upgrade_to = b.label_for(eye.m, eye.s, eye.c)
        if not enforce and label is None:
            # Limitation off: the steep-meridian range alone picks the label.
            for r in b.rows:
                if r.steep_min <= eye.m <= r.steep_max:
                    label, upgrade_to = r.label, r.upgrade_to
                    break
        out[idx] = EyeOption(idx, p, label, upgrade_to, b)
    return out


def free_upgrade(opts):
    """{from_index: to_index} where the eye's label says "Free Upgrade to X"
    and X is available for this eye (§1.2.5, Q9=A)."""
    fu = {}
    for idx, o in opts.items():
        if o.label == C.LABEL_FREE_UPGRADE and o.upgrade_to in opts and o.upgrade_to != idx:
            fu[idx] = o.upgrade_to
    return fu


def effective_price(opts, fu, idx):
    """Price this eye pays at `idx`: a free-upgrade target costs what the
    source index costs."""
    for src, dst in fu.items():
        if dst == idx:
            return min(opts[src].price, opts[idx].price)
    return opts[idx].price


def eye_recommendation(blocks, opts, eye):
    """Single-eye recommended index (§1.2.4)."""
    if not opts:
        return None
    fu = free_upgrade(opts)
    shown = {i for i in opts if i not in fu}
    good = []
    for i in shown:
        o = opts[i]
        is_fu_target = i in fu.values()
        if o.label in (C.LABEL_RECOMMENDED, C.LABEL_FREE_UPGRADE) or is_fu_target:
            good.append((effective_price(opts, fu, i), -i, i))
    if good:
        return sorted(good)[0][2]
    # No Recommended row: from the index whose steep range holds m, go up.
    bracket = min((i for i, b in blocks.items() if b.steep_covers(eye.m)), default=None)
    ordered = sorted(shown)
    if bracket is not None:
        up = [i for i in ordered if i >= bracket]
        if up:
            return up[0]
    return ordered[-1] if ordered else None


# ── pair / card ──────────────────────────────────────────────────────────────

@dataclass
class CardOption:
    index: Decimal
    price: Decimal
    material: str
    recommended: bool
    free_upgrade: bool
    charged_index: Decimal
    blocks: list            # refs (od, os)
    eye_prices: dict

    def as_dict(self):
        return {"index": str(self.index), "price": str(self.price), "material": self.material,
                "recommended": self.recommended, "free_upgrade": self.free_upgrade,
                "charged_index": str(self.charged_index), "blocks": self.blocks,
                "eye_prices": {k: str(v) for k, v in self.eye_prices.items()}}


@dataclass
class Card:
    line: str
    display_name: str
    description: str
    recommended_index: Decimal
    options: list           # [CardOption] ascending index
    fallback: str = ""      # "up" / "down" when Q2 target was not common

    def option(self, index):
        index = Q(index)
        return next((o for o in self.options if o.index == index), None)

    def as_dict(self):
        return {"line": self.line, "display_name": self.display_name, "description": self.description,
                "recommended_index": str(self.recommended_index), "fallback": self.fallback or None,
                "options": [o.as_dict() for o in self.options]}


def _card_for_line(catalog, cfg, line, eyes, sel):
    per_eye = {}
    for name, eye in eyes.items():
        blocks = product_blocks(catalog, cfg, line.code, eye.rx_type, sel)
        opts = eye_options(blocks, eye, cfg)
        rec = eye_recommendation(blocks, opts, eye)
        per_eye[name] = (blocks, opts, free_upgrade(opts), rec)
    if any(v[3] is None for v in per_eye.values()):
        return None
    (b_od, o_od, fu_od, r_od), (b_os, o_os, fu_os, r_os) = per_eye["od"], per_eye["os"]
    od, os_ = eyes["od"], eyes["os"]

    # Q2: higher of the two recommendations; equal meridians with one eye
    # near and one far → the farsighted eye's recommendation.
    if od.m == os_.m and od.rx_type != os_.rx_type and {od.rx_type, os_.rx_type} == {"SV_NEAR", "SV_FAR"}:
        target = r_od if od.rx_type == "SV_FAR" else r_os
    else:
        target = max(r_od, r_os)

    common = sorted(set(o_od) & set(o_os))
    # A free-upgrade source index is hidden only when BOTH eyes upgrade it.
    pair_fu = {src: dst for src, dst in fu_od.items() if fu_os.get(src) == dst and dst in common}
    shown = [i for i in common if i not in pair_fu]
    if not shown:
        return None
    fallback = ""
    if target in pair_fu:
        target = pair_fu[target]
    if target not in shown:
        up = [i for i in shown if i > target]
        down = [i for i in shown if i < target]
        if up:
            target, fallback = up[0], "up"
        elif down:
            target, fallback = down[-1], "down"
        else:
            return None

    n = int(cfg.get("neighbor_count", 1))
    pos = shown.index(target)
    picked = shown[max(0, pos - n): pos + n + 1]
    options = []
    for i in picked:
        p_od = effective_price(o_od, fu_od, i)
        p_os = effective_price(o_os, fu_os, i)
        is_fu = i in pair_fu.values()
        charged = next((s for s, d in pair_fu.items() if d == i), i)
        options.append(CardOption(
            index=i, price=max(p_od, p_os), material=o_od[i].block.material or o_os[i].block.material,
            recommended=(i == target), free_upgrade=is_fu, charged_index=charged,
            blocks=[dict(o_od[i].block.ref(), eye="od"), dict(o_os[i].block.ref(), eye="os")],
            eye_prices={"od": p_od, "os": p_os}))
    return Card(line=line.code, display_name=line.display_name, description=line.description,
                recommended_index=target, options=options, fallback=fallback)


@dataclass
class Quote:
    category: str
    selection: Selection
    eyes: dict              # name -> PricingEye
    cards: list = field(default_factory=list)
    blocked_reason: str = ""

    @property
    def available(self):
        return bool(self.cards) and not self.blocked_reason

    def card(self, line):
        return next((c for c in self.cards if c.line == line), None)

    def as_dict(self):
        return {
            "category": self.category, "selection": self.selection.as_dict() if self.selection else None,
            "pricing_rx": {k: v.as_dict() for k, v in self.eyes.items()},
            "cards": [c.as_dict() for c in self.cards],
            "available": self.available,
            "unavailable_reason": self.blocked_reason or (None if self.cards else REASON_NO_RX),
        }


def make_eyes(category, od, os_):
    if category == NON_RX:
        od = os_ = EyeRx()
    return {"od": pricing_eye(od, category), "os": pricing_eye(os_, category)}


def over_max_cyl(cfg, od, os_):
    lim = Decimal(str(cfg.get("max_cyl", "6.00")))
    return abs(Q(od.cyl or 0)) > lim or abs(Q(os_.cyl or 0)) > lim


def quote(catalog, cfg, category, od, os_, sel):
    """Cards (one per line that can make this pair), §1.3–1.4."""
    if category not in (SV, BIFOCAL, PROGRESSIVE, NON_RX):
        raise SelectionError("use quote_reader for READERS")
    validate_selection(sel)
    eyes = make_eyes(category, od, os_)
    q = Quote(category=category, selection=sel, eyes=eyes)
    if category != NON_RX and over_max_cyl(cfg, od, os_):
        q.blocked_reason = REASON_MAX_CYL.format(max_cyl=cfg.get("max_cyl", "6.00"))
        return q
    for line in catalog.lines:
        card = _card_for_line(catalog, cfg, line, eyes, sel)
        if card is not None:
            q.cards.append(card)
    return q


# ── Readers (§1.6) ───────────────────────────────────────────────────────────

def reader_powers(cfg):
    return C.power_steps(cfg["reader_min"], cfg["reader_max"], cfg["reader_step"])


def quote_reader(catalog, cfg, power):
    """[{coating, label, price, index, charged_index, block}] for one power.
    S=+power, C=0 on the farsighted table of cfg.reader_line; index picked by
    §1.2 and not shown to the customer."""
    power = Q(power)
    if power not in reader_powers(cfg):
        raise SelectionError(f"reader power must be one of {', '.join('+' + str(p) for p in reader_powers(cfg))}")
    line = catalog.line_by_code.get(cfg["reader_line"])
    out = []
    if line is None:
        return out
    eye = PricingEye(sph=power, cyl=Decimal("0"), axis=None, s=power, c=Decimal("0.00"), m=power,
                     rx_type=cfg.get("reader_rx_type", "SV_FAR"))
    for coat in cfg["reader_coatings"]:
        sel = Selection(lens_type=cfg.get("reader_lens_type", "CLEAR"), coating=coat["code"])
        blocks = product_blocks(catalog, cfg, line.code, eye.rx_type, sel)
        opts = eye_options(blocks, eye, cfg)
        rec = eye_recommendation(blocks, opts, eye)
        if rec is None:
            continue
        fu = free_upgrade(opts)
        charged = next((s for s, d in fu.items() if d == rec), rec)
        out.append({"coating": coat["code"], "label": coat["label"], "line": line.code,
                    "price": effective_price(opts, fu, rec), "index": rec, "charged_index": charged,
                    "block": opts[rec].block.ref()})
    return out


# ── step options (§3.4: only show what at least one line can price) ─────────

def selections_for(catalog, cfg, category):
    """Every concrete Selection the active table can describe for this
    category (before checking the prescription)."""
    rx_types = {SV: ("SV_NEAR", "SV_FAR"), NON_RX: ("SV_NEAR",), BIFOCAL: ("BIFOCAL",),
                PROGRESSIVE: ("PROGRESSIVE",)}[category]
    seen = set()
    for b in catalog.blocks:
        if b.rx_type not in rx_types:
            continue
        if b.lens_type == "CLEAR":
            if b.coating in ("N", "BLUE") and not b.colors:
                seen.add(Selection("CLEAR", coating=b.coating))
        elif b.lens_type == "PHOTOCHROMIC":
            if b.coating in ("N", "BLUE"):
                for col in b.colors:
                    seen.add(Selection("PHOTOCHROMIC", color=col, coating=b.coating))
        elif b.lens_type == "SUN":
            if b.coating in ("POLARIZED", "MIRRORED"):
                for col in b.colors:
                    seen.add(Selection("SUN", tint=b.coating, color=col))
            elif b.coating in ("N", "BLUE"):
                tints = ["SOLID"] + (["GRADIENT"] if cfg.get("gradient_enabled", True) else [])
                for col in b.colors:
                    for d in b.depths:
                        for t in tints:
                            seen.add(Selection("SUN", tint=t, color=col, depth=d, coating=b.coating))
    return seen


def available_selections(catalog, cfg, category, od, os_):
    """{Selection: [line codes]} for selections that give at least one card."""
    eyes = make_eyes(category, od, os_)
    if category != NON_RX and over_max_cyl(cfg, od, os_):
        return {}
    out = {}
    for sel in selections_for(catalog, cfg, category):
        lines = [ln.code for ln in catalog.lines if _card_for_line(catalog, cfg, ln, eyes, sel) is not None]
        if lines:
            out[sel] = lines
    return out
