"""
Lens price table: Excel file <-> database.

The Excel layout (one sheet per tier, "Premium Lens" and "Economic Lens"):

    row 1        title, e.g. "Premium Lens (Conant)"          (ignored)
    header row   Recommended SE | Limitation S | Limitation C | Rationale |
                 Prescription Type | Lens Type | Color | Depth | Coating |
                 Index | Material | Sphere/Cylinder | <cylinder powers...>
                 Columns are found by their header text, so they may be in
                 any order and Recommended SE, Limitation S/C and Rationale
                 may be left out; the cylinder powers must come after
                 Sphere/Cylinder.
    data rows    the first row carries the block's text columns; every row
                 has a sphere power ("Plano" or a number) and a price, or "N"
                 for not available, under each cylinder power. Text in the
                 Recommended SE column below the first row is kept as a note
                 (e.g. "Free Upgrade to 1.56").
    ... the next header row starts the next block; blocks follow each other.

A price means the lens exists for that sphere/cylinder; "N" means it doesn't.

`parse_workbook` checks a file and reports every problem with its sheet and
cell (nothing is touched); `apply_import` replaces the sheets' blocks in the
database; `build_workbook` writes the current table in the same layout, so
export -> edit -> import round-trips.
"""
import io
import re
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

import openpyxl
from django.core.files.base import ContentFile
from django.db import transaction
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .models import LensPriceBlock, LensPriceCell, LensPriceImport

# (tier code, sheet name, title written in A1)
TIERS = [
    ("premium", "Premium Lens", "Premium Lens (Conant)"),
    ("economic", "Economic Lens", "Economic Lens (Value)"),
]
SHEET_TO_TIER = {name.lower(): code for code, name, _ in TIERS}

# Header text (lower case) -> field. "Shpere" is a typo that appeared in older files.
COLUMNS = {
    "recommended se": "recommended_se", "limitation s": "limitation_s",
    "limitation c": "limitation_c", "rationale": "rationale",
    "prescription type": "prescription_type", "lens type": "lens_type",
    "color": "color", "depth": "depth", "coating": "coating",
    "index": "index", "material": "material",
    "sphere/cylinder": "sphere", "shpere/cylinder": "sphere",
}
REQUIRED = ["prescription_type", "lens_type", "index", "sphere"]
EXPORT_HEADER = [
    "Recommended SE", "Limitation S", "Limitation C", "Rationale",
    "Prescription Type", "Lens Type", "Color", "Depth", "Coating",
    "Index", "Material", "Sphere/Cylinder",
]
EXPORT_SPHERE_COL = 12     # L
MAX_PRICE = Decimal("100000")
CENTS = Decimal("0.01")


# ── Reporting ────────────────────────────────────────────────────────────────

@dataclass
class Problem:
    sheet: str
    cell: str
    message: str


@dataclass
class BlockData:
    tier: str
    position: int
    header_row: int
    recommended_se: str = ""
    limitation_s: str = ""
    limitation_c: str = ""
    rationale: str = ""
    note: str = ""
    prescription_type: str = ""
    lens_type: str = ""
    color: str = "N"
    depth: str = "N"
    coating: str = "N"
    lens_index: Decimal = Decimal("0")
    material: str = ""
    sphere_axis: list = field(default_factory=list)      # [Decimal]
    cylinder_axis: list = field(default_factory=list)    # [Decimal]
    prices: dict = field(default_factory=dict)           # (sphere, cyl) -> Decimal
    refs: dict = field(default_factory=dict)             # (sphere, cyl) -> "L12"
    first_cyl_col: int = 13

    @property
    def key(self):
        return (self.prescription_type, self.lens_type, self.color,
                self.depth, self.coating, self.lens_index)

    def label(self):
        return (f"{self.prescription_type} / {self.lens_type} / {self.color} / "
                f"{self.depth} / {self.coating} / index {self.lens_index}")


@dataclass
class ParseResult:
    blocks: dict = field(default_factory=lambda: defaultdict(list))   # tier -> [BlockData]
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    @property
    def ok(self):
        return not self.errors

    def summary(self):
        out = {}
        for code, name, _ in TIERS:
            blocks = self.blocks.get(code)
            if blocks is not None:
                out[name] = {
                    "blocks": len(blocks),
                    "priced_cells": sum(len(b.prices) for b in blocks),
                    "blocks_without_prices": sum(1 for b in blocks if not b.prices),
                }
        return out


# ── Cell helpers ─────────────────────────────────────────────────────────────

def _text(value):
    """Cell -> clean single-spaced text ('' for empty). Normalises the
    non-breaking hyphens/minus signs Excel files tend to contain."""
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    s = str(value)
    for ch in ("‑", "‐", "−", "–"):
        s = s.replace(ch, "-")
    return re.sub(r"\s+", " ", s).strip()


def _number(value):
    """Cell -> Decimal, or None when it isn't a number."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(_text(value))
    except (InvalidOperation, ValueError):
        return None


def _power(value):
    """Sphere/cylinder label -> Decimal ('Plano' is 0), or None."""
    if _text(value).lower() == "plano":
        return Decimal("0")
    n = _number(value)
    return n.quantize(CENTS, rounding=ROUND_HALF_UP) if n is not None else None


def _ref(col, row):
    return f"{get_column_letter(col)}{row}"


# ── Parsing ──────────────────────────────────────────────────────────────────

def parse_workbook(fileobj):
    """Check an uploaded .xlsx. Returns a ParseResult; if `.errors` is empty
    the blocks in it are safe to hand to `apply_import`."""
    result = ParseResult()
    try:
        wb = openpyxl.load_workbook(fileobj, read_only=True, data_only=True)
    except Exception:  # noqa: BLE001 - zipfile/openpyxl raise many types
        result.errors.append(Problem(
            "(file)", "", "This is not a valid .xlsx file. Upload an Excel workbook "
                          "(.xlsx), for example one downloaded from this page."))
        return result

    seen_tiers = set()
    for ws in wb.worksheets:
        tier = SHEET_TO_TIER.get(_text(ws.title).lower())
        if tier is None:
            result.errors.append(Problem(
                ws.title, "", f'Unknown sheet "{ws.title}". The file must only contain '
                              f'the sheets: {", ".join(n for _, n, _ in TIERS)}.'))
            continue
        seen_tiers.add(tier)
        _parse_sheet(ws, tier, result)

    if not seen_tiers and not any(e.sheet != "(file)" for e in result.errors):
        result.errors.append(Problem(
            "(file)", "", "No price sheets found. Expected sheets named "
                          + " and ".join(f'"{n}"' for _, n, _ in TIERS) + "."))
    for code, name, _ in TIERS:
        if code not in seen_tiers and seen_tiers:
            result.warnings.append(Problem(
                name, "", f'The file has no "{name}" sheet, so its current prices stay as they are.'))
    if result.ok:
        _quality_warnings(result)
    return result


def _parse_sheet(ws, tier, result):
    sheet = ws.title
    rows = [list(r) for r in ws.iter_rows(values_only=True)]
    err = lambda cell, msg: result.errors.append(Problem(sheet, cell, msg))      # noqa: E731
    warn = lambda cell, msg: result.warnings.append(Problem(sheet, cell, msg))   # noqa: E731

    def cell(r, c):  # 1-based, tolerant of short rows
        row = rows[r - 1]
        return row[c - 1] if c - 1 < len(row) else None

    # Every block starts with a header row; find them by the label "Recommended SE"
    # in column A, or, when that column was left out, by "Prescription Type".
    def is_header(row):
        labels = {_text(v).lower() for v in row[:15] if v is not None}
        return "recommended se" in labels or ("prescription type" in labels and "lens type" in labels)

    header_rows = [i + 1 for i, row in enumerate(rows) if row and is_header(row)]
    if not header_rows:
        err("A1", 'No block headers found. Each block must start with a header row '
                  '(Recommended SE | Limitation S | ... | Prescription Type | Lens Type | ... | Sphere/Cylinder | cylinder powers).')
        return

    for r in range(2, header_rows[0]):
        for c in range(1, 16):
            v = cell(r, c)
            if v is not None and _text(v):
                warn(_ref(c, r), f'Text above the first header row is ignored: "{_text(v)}".')

    blocks = []
    for n, h in enumerate(header_rows):
        end = (header_rows[n + 1] - 1) if n + 1 < len(header_rows) else len(rows)
        block = _parse_block(sheet, tier, len(blocks), h, end, cell, result)
        if block is not None:
            blocks.append(block)

    # duplicate lens definitions
    by_key = defaultdict(list)
    for b in blocks:
        by_key[b.key].append(b)
    for key, dup in by_key.items():
        if len(dup) > 1:
            where = ", ".join(f"row {b.header_row}" for b in dup)
            err(f"A{dup[1].header_row}",
                f"The same lens is defined more than once ({where}): {dup[0].label()}. "
                "Each combination of prescription type, lens type, color, depth, coating and index "
                "may only appear once.")
    result.blocks[tier] = blocks


def _read_header(h, cell, err):
    """Header row -> {field: column} (including "sphere"), or None. The text
    columns are read left to right up to Sphere/Cylinder; the cylinder powers
    are to its right."""
    cols = {}
    names = sorted({"Recommended SE" if k == "recommended se" else k.title()
                    for k in COLUMNS if k != "shpere/cylinder"})
    for c in range(1, 41):
        raw = cell(h, c)
        label = _text(raw).lower()
        if label == "":
            continue
        field_name = COLUMNS.get(label)
        if field_name is None:
            err(_ref(c, h), f'Unknown column header "{_text(raw)}". Expected: ' + ", ".join(names) + ".")
        elif field_name in cols:
            err(_ref(c, h), f'Column "{_text(raw)}" appears twice in this header row.')
        else:
            cols[field_name] = c
        if field_name == "sphere":
            break
    else:
        err(_ref(1, h), 'This header row has no "Sphere/Cylinder" column.')
        return None
    for field_name in REQUIRED:
        if field_name not in cols:
            nice = next(k for k, v in COLUMNS.items() if v == field_name).title()
            err(_ref(1, h), f'This header row is missing the "{nice}" column.')
    return cols


def _parse_block(sheet, tier, position, h, end, cell, result):
    err = lambda c, msg: result.errors.append(Problem(sheet, c, msg))       # noqa: E731
    warn = lambda c, msg: result.warnings.append(Problem(sheet, c, msg))    # noqa: E731
    n_errors_before = len(result.errors)
    block = BlockData(tier=tier, position=position, header_row=h)

    cols = _read_header(h, cell, err)
    if cols is None or len(result.errors) > n_errors_before:
        return None
    sphere_col = cols["sphere"]
    first_cyl = sphere_col + 1

    # cylinder axis (right of Sphere/Cylinder until the first empty header cell)
    cyl_cols = []
    c = first_cyl
    while cell(h, c) is not None and _text(cell(h, c)) != "":
        p = _power(cell(h, c))
        if p is None:
            err(_ref(c, h), f'Cylinder power must be "Plano" or a number, but is "{_text(cell(h, c))}".')
        elif p in [x for _, x in cyl_cols]:
            err(_ref(c, h), f"Cylinder power {p} appears twice in this header row.")
        else:
            cyl_cols.append((c, p))
        c += 1
    if not cyl_cols and len(result.errors) == n_errors_before:
        err(_ref(first_cyl, h), f"This header row has no cylinder powers (columns {get_column_letter(first_cyl)} onwards).")
    block.cylinder_axis = [p for _, p in cyl_cols]
    block.first_cyl_col = first_cyl

    # text columns: first non-empty value in the block
    def first_text(field_name, default=""):
        col = cols.get(field_name)
        if col is None:
            return default, 0
        for r in range(h + 1, end + 1):
            v = _text(cell(r, col))
            if v:
                return v, r
        return default, 0

    block.recommended_se = first_text("recommended_se")[0]
    block.limitation_s = first_text("limitation_s")[0]
    block.limitation_c = first_text("limitation_c")[0]
    block.rationale = first_text("rationale")[0]
    block.prescription_type = first_text("prescription_type")[0]
    block.lens_type = first_text("lens_type")[0]
    block.color = first_text("color", "N")[0] or "N"
    block.depth = first_text("depth", "N")[0] or "N"
    block.coating = first_text("coating", "N")[0] or "N"
    block.material = first_text("material")[0]
    notes = []
    if "recommended_se" in cols:
        for r in range(h + 1, end + 1):
            v = _text(cell(r, cols["recommended_se"]))
            if v and v != block.recommended_se:
                notes.append(v)
    block.note = "; ".join(notes)[:255]

    if not block.prescription_type:
        err(_ref(cols["prescription_type"], h + 1), f"Prescription Type is empty in the block that starts at row {h}.")
    if not block.lens_type:
        err(_ref(cols["lens_type"], h + 1), f"Lens Type is empty in the block that starts at row {h}.")
    idx_text, idx_row = first_text("index")
    idx = _number(idx_text) if idx_text else None
    if idx is None:
        err(_ref(cols["index"], h + 1), f"Index must be a number such as 1.56 (block starting at row {h}).")
    elif not (Decimal("1") <= idx < Decimal("2")):
        err(_ref(cols["index"], idx_row), f"Index {idx} is outside the expected 1.00 - 1.99 range.")
    else:
        block.lens_index = idx.quantize(CENTS, rounding=ROUND_HALF_UP)
    for field_name, label in (("color", "Color"), ("depth", "Depth"), ("coating", "Coating")):
        if field_name in cols and not first_text(field_name)[0]:
            warn(_ref(cols[field_name], h + 1),
                 f'{label} is empty for the lens at row {h}; it is treated as "N" (none).')
    if "material" in cols and not block.material:
        warn(_ref(cols["material"], h + 1), f"Material is empty for {block.label()}.")

    # sphere rows
    seen_sphere = {}
    sph_letter = get_column_letter(sphere_col)
    for r in range(h + 1, end + 1):
        label = cell(r, sphere_col)
        grid = [(c, cell(r, c)) for c, _ in cyl_cols]
        if _text(label) == "":
            numbers = [(c, v) for c, v in grid if _number(v) is not None]
            texts = [(c, v) for c, v in grid if v is not None and _text(v) and _text(v).upper() != "N"
                     and _number(v) is None]
            if numbers:
                err(_ref(numbers[0][0], r),
                    f"This row has prices but no sphere power in column {sph_letter}.")
            elif texts:
                warn(_ref(texts[0][0], r),
                     f'Row {r} has no sphere power in column {sph_letter}, so it is ignored '
                     f'(it contains text such as "{_text(texts[0][1])}").')
            continue
        sphere = _power(label)
        if sphere is None:
            err(_ref(sphere_col, r), f'Sphere power must be "Plano" or a number, but is "{_text(label)}".')
            continue
        if sphere in seen_sphere:
            err(_ref(sphere_col, r), f"Sphere power {sphere} is listed twice in this block "
                                     f"(also on row {seen_sphere[sphere]}).")
            continue
        seen_sphere[sphere] = r
        block.sphere_axis.append(sphere)
        for c, cyl in cyl_cols:
            v = cell(r, c)
            ref = _ref(c, r)
            if v is None or _text(v) == "":
                err(ref, "Empty cell. Enter a price, or N if this power is not available.")
                continue
            if isinstance(v, str) and _text(v).upper() == "N":
                continue
            price = _number(v)
            if price is None:
                err(ref, f'Price must be a number, or N if not available, but is "{_text(v)}".')
            elif price <= 0:
                err(ref, f"Price must be greater than 0 (use N if not available), but is {price}.")
            elif price > MAX_PRICE:
                err(ref, f"Price {price} is unreasonably large.")
            else:
                block.prices[(sphere, cyl)] = price.quantize(CENTS, rounding=ROUND_HALF_UP)
                block.refs[(sphere, cyl)] = ref

    if not block.sphere_axis and len(result.errors) == n_errors_before:
        err(_ref(sphere_col, h + 1), f"The block starting at row {h} has no sphere rows.")
    return block


def _quality_warnings(result):
    """Problems that don't stop an import but are probably typos. (A higher
    index costing less than a lower one is NOT flagged: it happens with real
    stock/custom price differences and the cheaper lens is simply recommended.)"""
    for tier, blocks in result.blocks.items():
        sheet = next(n for c, n, _ in TIERS if c == tier)
        warn = lambda cell, msg: result.warnings.append(Problem(sheet, cell, msg))   # noqa: E731

        for b in blocks:
            # a cylinder column with no prices between columns that have prices
            has = [any((s, c) in b.prices for s in b.sphere_axis) for c in b.cylinder_axis]
            idx = [i for i, v in enumerate(has) if v]
            if idx:
                for i in range(idx[0], idx[-1]):
                    if not has[i]:
                        col = b.first_cyl_col + i
                        warn(f"{get_column_letter(col)}{b.header_row + 1}",
                             f"Cylinder {b.cylinder_axis[i]} has no price on any row of the block at "
                             f"row {b.header_row} ({b.label()}), but the powers on both sides do.")


# ── Applying ─────────────────────────────────────────────────────────────────

def _axis_json(values):
    return [str(v) for v in values]


@transaction.atomic
def apply_import(result, *, user=None, filename="", file_bytes=None):
    """Replace the price table for every sheet that was in the file. Call
    only with a ParseResult that has no errors."""
    if not result.ok:
        raise ValueError("Cannot import a file that has errors.")
    for tier, blocks in result.blocks.items():
        LensPriceBlock.objects.filter(tier=tier).delete()
        for b in blocks:
            row = LensPriceBlock.objects.create(
                tier=tier, position=b.position,
                recommended_se=b.recommended_se[:60], limitation_s=b.limitation_s[:40],
                limitation_c=b.limitation_c[:40], rationale=b.rationale, note=b.note,
                prescription_type=b.prescription_type[:100], lens_type=b.lens_type[:100],
                color=b.color[:100], depth=b.depth[:50], coating=b.coating[:100],
                lens_index=b.lens_index, material=b.material[:100],
                sphere_axis=_axis_json(b.sphere_axis), cylinder_axis=_axis_json(b.cylinder_axis))
            LensPriceCell.objects.bulk_create(
                [LensPriceCell(block=row, sphere=s, cylinder=c, price=p)
                 for (s, c), p in b.prices.items()],
                batch_size=2000)
    record = LensPriceImport(
        uploaded_by=user if getattr(user, "is_authenticated", False) else None,
        original_filename=filename[:255], summary=result.summary(),
        warning_count=len(result.warnings))
    if file_bytes is not None:
        record.file.save(filename or "lens-prices.xlsx", ContentFile(file_bytes), save=False)
    record.save()
    return record


# ── Exporting ────────────────────────────────────────────────────────────────

def _axis_label(value):
    return "Plano" if value == 0 else float(value)


def build_workbook():
    """The current table as an .xlsx (bytes), in the layout `parse_workbook` reads."""
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    bold = Font(bold=True)
    head_fill = PatternFill("solid", fgColor="EEEEEE")
    first_cyl = EXPORT_SPHERE_COL + 1
    for code, name, title in TIERS:
        ws = wb.create_sheet(name)
        ws["A1"] = title
        ws["A1"].font = Font(bold=True, size=14)
        r = 3
        blocks = (LensPriceBlock.objects.filter(tier=code)
                  .prefetch_related("cells").order_by("position", "id"))
        for b in blocks:
            spheres = [Decimal(x) for x in b.sphere_axis]
            cyls = [Decimal(x) for x in b.cylinder_axis]
            prices = {(c.sphere, c.cylinder): c.price for c in b.cells.all()}
            for c, label in enumerate(EXPORT_HEADER, start=1):
                ws.cell(r, c, label)
            for i, cyl in enumerate(cyls):
                ws.cell(r, first_cyl + i, _axis_label(cyl))
            for c in range(1, first_cyl + len(cyls)):
                ws.cell(r, c).font = bold
                ws.cell(r, c).fill = head_fill
            for n, sphere in enumerate(spheres):
                row = r + 1 + n
                if n == 0:
                    meta = [b.recommended_se, b.limitation_s, b.limitation_c, b.rationale,
                            b.prescription_type, b.lens_type, b.color, b.depth, b.coating,
                            float(b.lens_index), b.material]
                    for c, v in enumerate(meta, start=1):
                        if v != "":
                            ws.cell(row, c, v)
                elif n == 1 and b.note:
                    ws.cell(row, 1, b.note)
                ws.cell(row, EXPORT_SPHERE_COL, _axis_label(sphere))
                for i, cyl in enumerate(cyls):
                    price = prices.get((sphere, cyl))
                    ws.cell(row, first_cyl + i, float(price) if price is not None else "N")
            r += 1 + len(spheres)
        ws.column_dimensions["A"].width = 24
        for letter in "EFGHI":
            ws.column_dimensions[letter].width = 22
        ws.column_dimensions["K"].width = 30
        ws.freeze_panes = "A2"
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ── Lookup (for the shopping flow) ───────────────────────────────────────────

@dataclass
class PriceLookup:
    """Result of `lookup_price`."""
    price: Decimal
    tier: str            # "premium" or "economic"
    lens_index: Decimal  # actual index used (may be 1.56 when 1.50 has a free upgrade)
    free_upgrade: bool   # True: 1.56 lens included at no extra cost


_FREE_UPGRADE_156 = Decimal("1.56")
_FREE_UPGRADE_TAG = "free upgrade to 1.56"


def price_for(tier, prescription_type, lens_type, color, depth, coating,
              lens_index, sphere, cylinder):
    """Price of one lens, or None. No fallback: use `lookup_price` for the
    full Premium -> Economic + free-upgrade logic."""
    block = LensPriceBlock.objects.filter(
        tier=tier, prescription_type=prescription_type, lens_type=lens_type,
        color=color or "N", depth=depth or "N", coating=coating or "N",
        lens_index=lens_index).first()
    if block is None:
        return None
    cell = block.cells.filter(sphere=sphere, cylinder=cylinder).first()
    return cell.price if cell else None


def _block_price(block, sphere, cylinder):
    """Price from one block, with the Free Upgrade to 1.56 rule.
    Returns (price, actual_lens_index, is_free_upgrade), or (None, index, False)."""
    cell = block.cells.filter(sphere=sphere, cylinder=cylinder).first()
    if cell is not None:
        return cell.price, block.lens_index, False
    combined = f"{block.note} {block.recommended_se}".lower()
    if _FREE_UPGRADE_TAG in combined and block.lens_index != _FREE_UPGRADE_156:
        upgrade = LensPriceBlock.objects.filter(
            tier=block.tier, prescription_type=block.prescription_type,
            lens_type=block.lens_type, color=block.color,
            depth=block.depth, coating=block.coating,
            lens_index=_FREE_UPGRADE_156).first()
        if upgrade:
            cell = upgrade.cells.filter(sphere=sphere, cylinder=cylinder).first()
            if cell is not None:
                return cell.price, _FREE_UPGRADE_156, True
    return None, block.lens_index, False


def lookup_price(prescription_type, lens_type, color, depth, coating,
                 lens_index, sphere, cylinder):
    """Full price lookup: Premium first, then Economic; with Free Upgrade to
    1.56 inside each tier. Returns a PriceLookup, or None when this lens is
    not available for these powers."""
    for tier in ("premium", "economic"):
        block = LensPriceBlock.objects.filter(
            tier=tier, prescription_type=prescription_type, lens_type=lens_type,
            color=color or "N", depth=depth or "N", coating=coating or "N",
            lens_index=lens_index).first()
        if block is None:
            continue
        price, actual_index, free_upgrade = _block_price(block, sphere, cylinder)
        if price is not None:
            return PriceLookup(price=price, tier=tier,
                               lens_index=actual_index, free_upgrade=free_upgrade)
    return None
