"""
Lens price table: Excel file <-> database.

The Excel layout (one sheet per tier, "Premium Lens" and "Economic Lens"):

    row 1        title, e.g. "Premium Lens (Conant)"          (ignored)
    header row   Recommended SE | Limitation S | Limitation C | Rationale |
                 Prescription Type | Lens Type | Coating Main | Coating Add-on |
                 Index | Material | Sphere/Cylinder | <cylinder powers...>
    data rows    first row carries the block's text columns (A-J); every row
                 has a sphere power in column K ("Plano" or a number) and a
                 price, or "N" for not available, under each cylinder power.
                 Text in column A below the first row is kept as a note
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

HEADER = [
    "Recommended SE", "Limitation S", "Limitation C", "Rationale",
    "Prescription Type", "Lens Type", "Coating Main", "Coating Add-on",
    "Index", "Material", "Sphere/Cylinder",
]
# the original files spell it "Shpere/Cylinder"; accept both
_HEADER_ALIASES = {"shpere/cylinder": "sphere/cylinder"}
SPHERE_COL = 11            # K
FIRST_CYL_COL = 12         # L
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
    coating_main: str = "N"
    coating_add_on: str = "N"
    lens_index: Decimal = Decimal("0")
    material: str = ""
    sphere_axis: list = field(default_factory=list)      # [Decimal]
    cylinder_axis: list = field(default_factory=list)    # [Decimal]
    prices: dict = field(default_factory=dict)           # (sphere, cyl) -> Decimal
    refs: dict = field(default_factory=dict)             # (sphere, cyl) -> "L12"

    @property
    def key(self):
        return (self.prescription_type, self.lens_type, self.coating_main,
                self.coating_add_on, self.lens_index)

    def label(self):
        return (f"{self.prescription_type} / {self.lens_type} / {self.coating_main} / "
                f"{self.coating_add_on} / index {self.lens_index}")


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

    header_rows = [i + 1 for i, row in enumerate(rows)
                   if row and _text(row[0]).lower() == "recommended se"]
    if not header_rows:
        err("A1", 'No block headers found. Each block must start with a header row '
                  'whose column A says "Recommended SE".')
        return

    first_header = header_rows[0]
    for r in range(1, first_header):
        for c in range(1, SPHERE_COL + 1):
            v = cell(r, c)
            if v is not None and r != 1 and _text(v):
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
                "Each combination of prescription type, lens type, coatings and index may only appear once.")
    result.blocks[tier] = blocks


def _parse_block(sheet, tier, position, h, end, cell, result):
    err = lambda c, msg: result.errors.append(Problem(sheet, c, msg))       # noqa: E731
    warn = lambda c, msg: result.warnings.append(Problem(sheet, c, msg))    # noqa: E731
    n_errors_before = len(result.errors)
    block = BlockData(tier=tier, position=position, header_row=h)

    # header labels
    for c, expected in enumerate(HEADER, start=1):
        got = _text(cell(h, c)).lower()
        got = _HEADER_ALIASES.get(got, got)
        if got != expected.lower():
            err(_ref(c, h), f'Header should be "{expected}" but is "{_text(cell(h, c))}".')

    # cylinder axis (L onwards until the first empty header cell)
    cyl_cols = []
    c = FIRST_CYL_COL
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
        err(_ref(FIRST_CYL_COL, h), "This header row has no cylinder powers (columns L onwards).")
    block.cylinder_axis = [p for _, p in cyl_cols]

    # text columns: first non-empty value in the block
    text = {}
    for c in range(1, 11):
        for r in range(h + 1, end + 1):
            v = _text(cell(r, c))
            if v:
                text[c] = (v, r)
                break
    block.recommended_se = text.get(1, ("", 0))[0]
    block.limitation_s = text.get(2, ("", 0))[0]
    block.limitation_c = text.get(3, ("", 0))[0]
    block.rationale = text.get(4, ("", 0))[0]
    block.prescription_type = text.get(5, ("", 0))[0]
    block.lens_type = text.get(6, ("", 0))[0]
    block.coating_main = text.get(7, ("N", 0))[0] or "N"
    block.coating_add_on = text.get(8, ("N", 0))[0] or "N"
    block.material = text.get(10, ("", 0))[0]
    notes = []
    for r in range(h + 1, end + 1):
        v = _text(cell(r, 1))
        if v and v != block.recommended_se:
            notes.append(v)
    block.note = "; ".join(notes)[:255]

    if not block.prescription_type:
        err(_ref(5, h + 1), f"Prescription Type is empty in the block that starts at row {h}.")
    if not block.lens_type:
        err(_ref(6, h + 1), f"Lens Type is empty in the block that starts at row {h}.")
    idx_text = text.get(9)
    idx = _number(idx_text[0]) if idx_text else None
    if idx is None:
        err(_ref(9, h + 1), f"Index must be a number such as 1.56 (block starting at row {h}).")
    elif not (Decimal("1") <= idx < Decimal("2")):
        err(_ref(9, idx_text[1]), f"Index {idx} is outside the expected 1.00 - 1.99 range.")
    else:
        block.lens_index = idx.quantize(CENTS, rounding=ROUND_HALF_UP)
    if not block.material:
        warn(_ref(10, h + 1), f"Material is empty for {block.label()}.")

    # sphere rows
    seen_sphere = {}
    for r in range(h + 1, end + 1):
        label = cell(r, SPHERE_COL)
        grid = [(c, cell(r, c)) for c, _ in cyl_cols]
        if _text(label) == "":
            numbers = [(c, v) for c, v in grid if _number(v) is not None]
            texts = [(c, v) for c, v in grid if v is not None and _text(v) and _text(v).upper() != "N"
                     and _number(v) is None]
            if numbers:
                err(_ref(numbers[0][0], r),
                    "This row has prices but no sphere power in column K.")
            elif texts:
                warn(_ref(texts[0][0], r),
                     f'Row {r} has no sphere power in column K, so it is ignored '
                     f'(it contains text such as "{_text(texts[0][1])}").')
            continue
        sphere = _power(label)
        if sphere is None:
            err(_ref(SPHERE_COL, r), f'Sphere power must be "Plano" or a number, but is "{_text(label)}".')
            continue
        if sphere in seen_sphere:
            err(_ref(SPHERE_COL, r), f"Sphere power {sphere} is listed twice in this block "
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
        err(_ref(SPHERE_COL, h + 1), f"The block starting at row {h} has no sphere rows.")
    return block


def _quality_warnings(result):
    """Problems that don't stop an import but are almost certainly typos."""
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
                        col = FIRST_CYL_COL + i
                        warn(f"{get_column_letter(col)}{b.header_row + 1}",
                             f"Cylinder {b.cylinder_axis[i]} has no price on any row of the block at "
                             f"row {b.header_row} ({b.label()}), but the powers on both sides do.")

        # a higher index costing less than a lower one at the same power
        families = defaultdict(dict)
        for b in blocks:
            families[(b.prescription_type, b.lens_type, b.coating_main, b.coating_add_on)][b.lens_index] = b
        for fam, by_index in families.items():
            order = sorted(by_index)
            for lo, hi in zip(order, order[1:]):
                a, z = by_index[lo], by_index[hi]
                bad = [k for k in a.prices if k in z.prices and z.prices[k] < a.prices[k]]
                if bad:
                    k = bad[0]
                    warn(z.refs[k],
                         f"{fam[0]} / {fam[1]} / {fam[2]} / {fam[3]}: at sphere {k[0]}, cylinder {k[1]} "
                         f"index {hi} costs {z.prices[k]} but index {lo} ({a.refs[k]}) costs {a.prices[k]}"
                         f" ({len(bad)} cells affected).")


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
                coating_main=b.coating_main[:100], coating_add_on=b.coating_add_on[:100],
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
            for c, label in enumerate(HEADER, start=1):
                ws.cell(r, c, label)
            for i, cyl in enumerate(cyls):
                ws.cell(r, FIRST_CYL_COL + i, _axis_label(cyl))
            for c in range(1, FIRST_CYL_COL + len(cyls)):
                ws.cell(r, c).font = bold
                ws.cell(r, c).fill = head_fill
            for n, sphere in enumerate(spheres):
                row = r + 1 + n
                if n == 0:
                    meta = [b.recommended_se, b.limitation_s, b.limitation_c, b.rationale,
                            b.prescription_type, b.lens_type, b.coating_main, b.coating_add_on,
                            float(b.lens_index), b.material]
                    for c, v in enumerate(meta, start=1):
                        if v != "":
                            ws.cell(row, c, v)
                elif n == 1 and b.note:
                    ws.cell(row, 1, b.note)
                ws.cell(row, SPHERE_COL, _axis_label(sphere))
                for i, cyl in enumerate(cyls):
                    price = prices.get((sphere, cyl))
                    ws.cell(row, FIRST_CYL_COL + i, float(price) if price is not None else "N")
            r += 1 + len(spheres)
        ws.column_dimensions["A"].width = 24
        for letter in "EFGH":
            ws.column_dimensions[letter].width = 22
        ws.column_dimensions["J"].width = 30
        ws.freeze_panes = "A2"
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ── Lookup (for the shopping flow) ───────────────────────────────────────────

def price_for(tier, prescription_type, lens_type, coating_main, coating_add_on,
              lens_index, sphere, cylinder):
    """Price of one lens for a prescription, or None when that lens doesn't
    exist for these powers (no price in the table)."""
    block = LensPriceBlock.objects.filter(
        tier=tier, prescription_type=prescription_type, lens_type=lens_type,
        coating_main=coating_main or "N", coating_add_on=coating_add_on or "N",
        lens_index=lens_index).first()
    if block is None:
        return None
    cell = block.cells.filter(sphere=sphere, cylinder=cylinder).first()
    return cell.price if cell else None
