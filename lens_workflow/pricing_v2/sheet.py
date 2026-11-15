"""Read the lens price file (price_v2.xlsx layout) into ParsedBlock objects.

No database access: `parse_workbook(fileobj, sheet_to_line, cfg, overrides)`
returns a ParseResult with blocks, errors and warnings. Errors stop an
import; warnings are written to the import report.

Layout (one sheet per product line):

    header row   Steep Meridian | Limitation S | Limitation C | Index |
                 Recommendation | Rationale | Prescription Type | Lens Type |
                 Color | Depth | Coating | Material | Sphere/Cylinder | cyl...
    first row    block texts + the first steep-meridian sub-row
    more rows    further sub-rows (Steep Meridian + Limitation + label), notes
    every row    sphere power under Sphere/Cylinder and a price / N per cyl

Columns are found by header text (aliases below), never by position, so
reordering columns is harmless. Known quirks of price_v2.xlsx that are
accepted: "Recommended" / blank header for the label column, "Coating Main"
for Depth, U+2011 hyphens, "±", depth "0.8", "a≤S≤b" written backwards, two
spellings of "Free Upgrade to (Index) 1.56", blank cells (= N, warned).
"""
import re
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

import openpyxl
from openpyxl.utils import get_column_letter, column_index_from_string

from . import config as C

CENTS = Decimal("0.01")
MAX_PRICE = Decimal("100000")

COLUMN_ALIASES = {
    "steep meridian": "steep", "recommended se": "steep",
    "limitation s": "lim_s", "limitation c": "lim_c",
    "index": "index",
    "recommendation": "label", "recommended": "label",
    "rationale": "rationale",
    "prescription type": "rx_type", "lens type": "lens_type",
    "color": "color", "colour": "color",
    "depth": "depth", "coating main": "depth",
    "coating": "coating", "material": "material",
    "sphere/cylinder": "sphere", "shpere/cylinder": "sphere",
}
REQUIRED = ("steep", "lim_s", "lim_c", "index", "rx_type", "lens_type", "sphere")


@dataclass
class Problem:
    level: str      # "error" / "warning"
    sheet: str
    cell: str
    message: str

    def as_dict(self):
        return {"level": self.level, "sheet": self.sheet, "cell": self.cell, "message": self.message}

    def __str__(self):
        where = f"{self.sheet}!{self.cell}" if self.cell else self.sheet
        return f"{self.level:7} {where}: {self.message}"


@dataclass
class SubRow:
    steep_min: Decimal
    steep_max: Decimal          # Decimal("99") for "~ Above"
    s_min: Decimal
    s_max: Decimal
    c_min: Decimal
    c_max: Decimal
    c_gt: bool                  # True: |C| must be > c_min ("C>-2.00")
    label: str                  # RECOMMENDED / AVAILABLE / FREE_UPGRADE
    upgrade_to: Decimal = None  # for FREE_UPGRADE
    raw: dict = field(default_factory=dict)
    row: int = 0

    def limitation_ok(self, s, c):
        if not (self.s_min <= s <= self.s_max):
            return False
        if self.c_gt:
            return c > self.c_min
        return self.c_min <= c <= self.c_max

    def as_dict(self):
        return {
            "steep_min": str(self.steep_min), "steep_max": str(self.steep_max),
            "s_min": str(self.s_min), "s_max": str(self.s_max),
            "c_min": str(self.c_min), "c_max": str(self.c_max), "c_gt": self.c_gt,
            "label": self.label, "upgrade_to": str(self.upgrade_to) if self.upgrade_to else None,
            "raw": self.raw, "row": self.row,
        }

    @classmethod
    def from_dict(cls, d):
        return cls(
            steep_min=Decimal(d["steep_min"]), steep_max=Decimal(d["steep_max"]),
            s_min=Decimal(d["s_min"]), s_max=Decimal(d["s_max"]),
            c_min=Decimal(d["c_min"]), c_max=Decimal(d["c_max"]), c_gt=bool(d["c_gt"]),
            label=d["label"], upgrade_to=Decimal(d["upgrade_to"]) if d.get("upgrade_to") else None,
            raw=d.get("raw") or {}, row=d.get("row") or 0)


@dataclass
class ParsedBlock:
    line: str
    sheet: str
    source_row: int
    position: int
    rx_type: str = ""
    lens_type: str = ""
    color_group: str = ""
    colors: list = field(default_factory=list)
    is_generic_color: bool = False
    depths: list = field(default_factory=list)
    coating: str = "N"
    lens_index: Decimal = Decimal("0")
    material: str = ""
    rationale: str = ""
    notes: str = ""
    raw: dict = field(default_factory=dict)
    rows: list = field(default_factory=list)          # [SubRow]
    grid: dict = field(default_factory=dict)          # (|S|, |C|) -> Decimal
    refs: dict = field(default_factory=dict)          # (|S|, |C|) -> "N12"

    @property
    def depths_key(self):
        return ",".join(str(d) for d in sorted(self.depths))

    @property
    def product_key(self):
        """Everything but the index: one product, several indexes."""
        return (self.line, self.rx_type, self.lens_type, self.color_group, self.depths_key, self.coating)

    @property
    def key(self):
        return self.product_key + (self.lens_index,)

    def label(self):
        return (f"{self.sheet} row {self.source_row}: {self.raw.get('rx_type')} / {self.raw.get('lens_type')} / "
                f"{self.raw.get('color')} / {self.raw.get('depth')} / {self.raw.get('coating')} / {self.lens_index}")

    def grid_json(self):
        return {f"{s}|{c}": str(p) for (s, c), p in sorted(self.grid.items())}


@dataclass
class ParseResult:
    blocks: list = field(default_factory=list)
    problems: list = field(default_factory=list)
    sheets: dict = field(default_factory=dict)       # sheet name -> line code
    overrides_applied: list = field(default_factory=list)

    @property
    def errors(self):
        return [p for p in self.problems if p.level == "error"]

    @property
    def warnings(self):
        return [p for p in self.problems if p.level == "warning"]

    @property
    def ok(self):
        return not self.errors


# ── text helpers ─────────────────────────────────────────────────────────────

_DASHES = ("‑", "‐", "−", "–", "—")


def text(value):
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    s = str(value)
    for ch in _DASHES:
        s = s.replace(ch, "-")
    s = s.replace(" ", " ").replace("\xa0", " ")
    return re.sub(r"\s+", " ", s).strip()


def number(value):
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float, Decimal)):
        return Decimal(str(value))
    try:
        return Decimal(text(value))
    except (InvalidOperation, ValueError):
        return None


def power(value):
    """Axis label → absolute power ('Plano' = 0)."""
    t = text(value).lower()
    if t == "plano":
        return Decimal("0.00")
    n = number(t.replace("+", "").replace("±", ""))
    return abs(n).quantize(CENTS, rounding=ROUND_HALF_UP) if n is not None else None


def _num(s):
    return abs(Decimal(s.replace("±", "").replace("+", "")))


_LIM_RANGE = re.compile(r"^([+±-]?\d+(?:\.\d+)?)\s*≤\s*([SC])\s*≤\s*([+±-]?\d+(?:\.\d+)?)$")
_LIM_LE = re.compile(r"^([SC])\s*(≤|<=)\s*([+±-]?\d+(?:\.\d+)?)$")
_LIM_GT = re.compile(r"^([SC])\s*>\s*([+±-]?\d+(?:\.\d+)?)$")
BIG = Decimal("99")


def parse_limitation(raw, which):
    """'S≤-4.00' / 'S≤±4.00' / 'S≤+4.00' → (min, max, gt) on absolute values.
    '-4.00≤S≤-8.00' (either order) → (4, 8, False). 'C>-2.00' → (2, 99, True).
    Raises ValueError."""
    s = text(raw).replace(" ", "")
    m = _LIM_RANGE.match(s)
    if m and m.group(2) == which:
        a, b = sorted([_num(m.group(1)), _num(m.group(3))])
        return a, b, False
    m = _LIM_LE.match(s)
    if m and m.group(1) == which:
        return Decimal("0"), _num(m.group(3)), False
    m = _LIM_GT.match(s)
    if m and m.group(1) == which:
        return _num(m.group(2)), BIG, True
    raise ValueError(f'cannot read Limitation {which} "{text(raw)}"')


_STEEP = re.compile(r"^(\d+(?:\.\d+)?)\s*D?\s*~\s*(\d+(?:\.\d+)?|above)\s*D?$", re.I)


def parse_steep(raw):
    s = text(raw)
    m = _STEEP.match(s)
    if not m:
        return None
    lo = Decimal(m.group(1))
    hi = BIG if m.group(2).lower() == "above" else Decimal(m.group(2))
    return lo, hi


_FREE = re.compile(r"free\s+upgrade\s+to\s+(?:index\s+)?(\d\.\d+)", re.I)


def parse_label(raw):
    """→ (label, upgrade_to) or raises ValueError."""
    s = text(raw)
    low = s.lower()
    m = _FREE.search(s)
    if m:
        return C.LABEL_FREE_UPGRADE, Decimal(m.group(1)).quantize(CENTS)
    if low == "recommended":
        return C.LABEL_RECOMMENDED, None
    if low == "available":
        return C.LABEL_AVAILABLE, None
    raise ValueError(f'unknown Recommendation "{s}" (expected Recommended / Available / Free Upgrade to 1.56)')


def parse_depths(raw):
    s = text(raw).lower()
    if s in ("", "n", "none"):
        return []
    out = set()
    for part in re.split(r"[,;/]", s):
        part = part.strip().replace(" ", "")
        if not part:
            continue
        n = number(part.rstrip("%"))
        if n is None:
            raise ValueError(f'cannot read Depth "{text(raw)}"')
        if n <= 1 and "%" not in part:
            n = n * 100
        out.add(int(n))
    return sorted(out)


def norm_key(raw):
    return text(raw).lower()


# ── overrides ────────────────────────────────────────────────────────────────

def _apply_overrides(rows_by_sheet, overrides, result):
    """overrides: [{"cell": "Premium Lens!D649", "from": 1.56, "to": 1.5, "source": "..."}].
    `from` must match the file (else error: the file changed, review the
    override). If the file already has `to`, warn that the override can go."""
    for o in overrides or []:
        ref = str(o.get("cell", ""))
        if "!" not in ref:
            result.problems.append(Problem("error", "(overrides)", ref, 'override "cell" must look like "Sheet!D649"'))
            continue
        sheet, addr = ref.rsplit("!", 1)
        rows = rows_by_sheet.get(sheet)
        m = re.fullmatch(r"([A-Z]+)(\d+)", addr.strip().upper())
        if rows is None or not m:
            result.problems.append(Problem("error", "(overrides)", ref, "override points at a sheet/cell that does not exist"))
            continue
        c = column_index_from_string(m.group(1)) - 1
        r = int(m.group(2)) - 1
        while len(rows) <= r:
            rows.append([])
        row = rows[r]
        while len(row) <= c:
            row.append(None)
        current = row[c]
        want_from, want_to = o.get("from"), o.get("to")
        same = lambda a, b: (number(a) is not None and number(b) is not None and number(a) == number(b)) or text(a) == text(b)  # noqa: E731
        if same(current, want_to):
            result.problems.append(Problem(
                "warning", sheet, addr, f'override not needed any more: the file already has "{text(want_to)}" '
                                        f'(remove it from the overrides file). Source: {o.get("source", "")}'))
            continue
        if not same(current, want_from):
            result.problems.append(Problem(
                "error", sheet, addr, f'override expects "{text(want_from)}" here but the file has "{text(current)}". '
                                      "The file changed — review the override."))
            continue
        row[c] = want_to
        result.overrides_applied.append({**o, "applied": True})


# ── parsing ──────────────────────────────────────────────────────────────────

def parse_workbook(fileobj, sheet_to_line, cfg=None, overrides=None):
    """sheet_to_line: {"economic lens": "economic", ...} (lower-case sheet names)."""
    cfg = cfg or C.defaults()
    result = ParseResult()
    try:
        wb = openpyxl.load_workbook(fileobj, read_only=True, data_only=True)
    except Exception:  # noqa: BLE001
        result.problems.append(Problem("error", "(file)", "", "not a readable .xlsx file"))
        return result
    rows_by_sheet = {}
    for ws in wb.worksheets:
        rows_by_sheet[ws.title] = [list(r) for r in ws.iter_rows(values_only=True)]
    wb.close()
    _apply_overrides(rows_by_sheet, overrides, result)

    for title, rows in rows_by_sheet.items():
        line = sheet_to_line.get(text(title).lower())
        if line is None:
            result.problems.append(Problem(
                "warning", title, "", "sheet ignored: no lens line is configured for it "
                                      "(admin → Lens lines: add one with this sheet name to sell it)"))
            continue
        result.sheets[title] = line
        _parse_sheet(title, line, rows, cfg, result)

    if not result.sheets:
        result.problems.append(Problem("error", "(file)", "", "no sheet matches a configured lens line"))

    seen = defaultdict(list)
    for b in result.blocks:
        seen[b.key].append(b)
    for key, dup in seen.items():
        if len(dup) > 1:
            rows = ", ".join(f"row {b.source_row}" for b in dup)
            result.problems.append(Problem(
                "error", dup[0].sheet, f"D{dup[1].source_row + 1}",
                f"the same lens is defined more than once ({rows}): {dup[0].label()}. "
                "Each product (prescription type, lens type, color, depth, coating) may list an index once."))
    if result.ok:
        _quality_warnings(result, cfg)
    return result


def _is_header(row):
    labels = {text(v).lower() for v in row[:40] if v is not None}
    return ("sphere/cylinder" in labels or "shpere/cylinder" in labels) and "prescription type" in labels


def _parse_sheet(sheet, line, rows, cfg, result):
    headers = [i + 1 for i, r in enumerate(rows) if r and _is_header(r)]
    if not headers:
        result.problems.append(Problem("error", sheet, "A1", "no block header rows (… | Prescription Type | … | Sphere/Cylinder | cylinders) found"))
        return
    position = 0
    for n, h in enumerate(headers):
        end = headers[n + 1] - 1 if n + 1 < len(headers) else len(rows)
        block = _parse_block(sheet, line, rows, h, end, cfg, result, position)
        if block is not None:
            result.blocks.append(block)
            position += 1


def _cell(rows, r, c):
    if r - 1 >= len(rows):
        return None
    row = rows[r - 1]
    return row[c - 1] if c - 1 < len(row) else None


def _read_header(sheet, rows, h, result):
    cols = {}
    sphere_col = None
    blank_cols = []
    for c in range(1, 41):
        label = text(_cell(rows, h, c)).lower()
        if not label:
            blank_cols.append(c)
            continue
        f = COLUMN_ALIASES.get(label)
        if f is None:
            result.problems.append(Problem("error", sheet, f"{get_column_letter(c)}{h}", f'unknown column header "{text(_cell(rows, h, c))}"'))
            continue
        if f in cols:
            result.problems.append(Problem("error", sheet, f"{get_column_letter(c)}{h}", f'column "{label}" appears twice'))
            continue
        cols[f] = c
        if f == "sphere":
            sphere_col = c
            break
    if sphere_col is None:
        result.problems.append(Problem("error", sheet, f"A{h}", 'header row has no "Sphere/Cylinder" column'))
        return None
    # The label column sometimes has no header text (9 blocks in price_v2):
    # accept a blank header right after Index.
    if "label" not in cols and "index" in cols and (cols["index"] + 1) in blank_cols:
        cols["label"] = cols["index"] + 1
    for f in REQUIRED:
        if f not in cols:
            result.problems.append(Problem("error", sheet, f"A{h}", f'header row is missing the "{f}" column'))
            return None
    return cols


def _parse_block(sheet, line, rows, h, end, cfg, result, position):
    def err(cell, msg):
        result.problems.append(Problem("error", sheet, cell, msg))

    def warn(cell, msg):
        result.problems.append(Problem("warning", sheet, cell, msg))

    n_before = len(result.errors)
    cols = _read_header(sheet, rows, h, result)
    if cols is None:
        return None
    ref = lambda f, r: f"{get_column_letter(cols[f])}{r}"   # noqa: E731
    sphere_col = cols["sphere"]

    cyl_cols = []
    c = sphere_col + 1
    while text(_cell(rows, h, c)) != "":
        p = power(_cell(rows, h, c))
        if p is None:
            err(f"{get_column_letter(c)}{h}", f'cylinder header must be "Plano" or a number, not "{text(_cell(rows, h, c))}"')
        else:
            cyl_cols.append((c, p))
        c += 1

    def first(f):
        if f not in cols:
            return "", 0
        for r in range(h + 1, end + 1):
            v = text(_cell(rows, r, cols[f]))
            if v:
                return v, r
        return "", 0

    rx_raw, rx_row = first("rx_type")
    has_prices = any(number(_cell(rows, r, cc)) is not None
                     for r in range(h + 1, end + 1) for cc, _ in cyl_cols)
    if not rx_raw:
        notes = [text(_cell(rows, r, cc)) for r in range(h + 1, end + 1) for cc in range(1, sphere_col)
                 if text(_cell(rows, r, cc))]
        if has_prices:
            err(f"A{h + 1}", "block has prices but no Prescription Type")
        else:
            warn(f"A{h}", "header without a product (note-only block) ignored"
                          + (f': "{notes[0][:80]}"' if notes else ""))
        return None

    b = ParsedBlock(line=line, sheet=sheet, source_row=h, position=position)
    lens_raw = first("lens_type")[0]
    color_raw = first("color")[0] if "color" in cols else "N"
    depth_raw = first("depth")[0] if "depth" in cols else "N"
    coating_raw = first("coating")[0] if "coating" in cols else "N"
    b.raw = {"rx_type": rx_raw, "lens_type": lens_raw, "color": color_raw,
             "depth": depth_raw, "coating": coating_raw}
    b.material = first("material")[0]
    b.rationale = first("rationale")[0]

    b.rx_type = cfg["rx_types"].get(norm_key(rx_raw), "")
    if not b.rx_type:
        err(ref("rx_type", rx_row), f'unknown Prescription Type "{rx_raw}"')
    b.lens_type = cfg["lens_types"].get(norm_key(lens_raw), "")
    if not b.lens_type:
        err(ref("lens_type", h + 1), f'unknown Lens Type "{lens_raw}"')
    if not color_raw:
        err(ref("color", h + 1), "Color is empty (write N for no tint)")
    else:
        key = norm_key(color_raw)
        if key not in cfg["color_groups"]:
            err(ref("color", h + 1), f'unknown Color "{color_raw}": add it to the colour groups in the settings')
        b.color_group = key
        b.colors = list(cfg["color_groups"].get(key, []))
        b.is_generic_color = key in cfg["generic_color_groups"]
    try:
        b.depths = parse_depths(depth_raw)
    except ValueError as exc:
        err(ref("depth", h + 1) if "depth" in cols else f"A{h}", str(exc))
    b.coating = cfg["coatings"].get(norm_key(coating_raw or "N"), "")
    if not b.coating:
        err(ref("coating", h + 1), f'unknown Coating "{coating_raw}"')

    idx_raw, idx_row = first("index")
    idx = number(idx_raw)
    if idx is None or not (Decimal("1") <= idx < Decimal("2")):
        err(ref("index", idx_row or h + 1), f'Index must be a number like 1.56, not "{idx_raw}"')
    else:
        b.lens_index = idx.quantize(CENTS, rounding=ROUND_HALF_UP)

    # sub-rows: any row with a Limitation; other texts are notes
    notes = []
    for r in range(h + 1, end + 1):
        steep_raw = text(_cell(rows, r, cols["steep"]))
        ls_raw = text(_cell(rows, r, cols["lim_s"]))
        lc_raw = text(_cell(rows, r, cols["lim_c"]))
        lab_raw = text(_cell(rows, r, cols["label"])) if "label" in cols else ""
        if not (ls_raw or lc_raw):
            for f in ("steep", "label", "lens_type", "index", "rationale"):
                if f in cols and r != h + 1:
                    v = text(_cell(rows, r, cols[f]))
                    if v and f in ("steep", "label", "lens_type"):
                        notes.append(v)
            continue
        if r != h + 1:
            ridx = number(_cell(rows, r, cols["index"]))
            if ridx is not None and b.lens_index and ridx.quantize(CENTS) != b.lens_index:
                err(ref("index", r), f"sub-row index {ridx} differs from the block index {b.lens_index}")
        steep = parse_steep(steep_raw)
        if steep is None:
            err(ref("steep", r), f'cannot read Steep Meridian "{steep_raw}" (expected like "2.25 ~ 4.00 D")')
            continue
        try:
            s_min, s_max, s_gt = parse_limitation(ls_raw, "S")
            c_min, c_max, c_gt = parse_limitation(lc_raw, "C")
            if s_gt:
                raise ValueError(f'"S>" limitations are not supported: "{ls_raw}"')
            label, upgrade_to = parse_label(lab_raw) if lab_raw else (None, None)
        except ValueError as exc:
            err(f"A{r}", str(exc))
            continue
        if label is None:
            err(ref("label", r) if "label" in cols else f"A{r}", "Recommendation is empty")
            continue
        b.rows.append(SubRow(steep[0], steep[1], s_min, s_max, c_min, c_max, c_gt, label, upgrade_to,
                             raw={"steep": steep_raw, "lim_s": ls_raw, "lim_c": lc_raw, "label": lab_raw}, row=r))
    b.notes = "; ".join(dict.fromkeys(notes))
    if not b.rows and len(result.errors) == n_before:
        err(f"A{h + 1}", "block has no Steep Meridian / Limitation row")

    # grid
    seen_s = {}
    for r in range(h + 1, end + 1):
        label = _cell(rows, r, sphere_col)
        if text(label) == "":
            if any(number(_cell(rows, r, cc)) is not None for cc, _ in cyl_cols):
                err(f"{get_column_letter(sphere_col)}{r}", "row has prices but no sphere power")
            continue
        s = power(label)
        if s is None:
            err(f"{get_column_letter(sphere_col)}{r}", f'sphere must be "Plano" or a number, not "{text(label)}"')
            continue
        if s in seen_s:
            err(f"{get_column_letter(sphere_col)}{r}", f"sphere {s} listed twice (also row {seen_s[s]})")
            continue
        seen_s[s] = r
        for cc, cyl in cyl_cols:
            v = _cell(rows, r, cc)
            cref = f"{get_column_letter(cc)}{r}"
            t = text(v)
            if t == "":
                warn(cref, "blank price cell treated as N (not available)")
                continue
            if t.upper() == "N":
                continue
            p = number(v)
            if p is None:
                err(cref, f'price must be a number or N, not "{t}"')
            elif p <= 0 or p > MAX_PRICE:
                err(cref, f"price {p} out of range")
            else:
                b.grid[(s, cyl)] = p.quantize(CENTS, rounding=ROUND_HALF_UP)
                b.refs[(s, cyl)] = cref
    return b


def limitation_ok(block, s, c):
    return any(r.limitation_ok(s, c) for r in block.rows)


def _quality_warnings(result, cfg):
    for b in result.blocks:
        outside = [k for k in b.grid if not limitation_ok(b, *k)]
        if outside:
            result.problems.append(Problem(
                "warning", b.sheet, f"A{b.source_row}",
                f"{len(outside)} priced cell(s) are outside the Limitation and are not sold while the "
                f"Limitation switch is on ({b.label()})"))
        if b.grid:
            ss = sorted({s for s, _ in b.grid} | {s for s, _ in b.refs})
            cs = sorted({c for _, c in b.grid})
            smax, cmax = max(ss), max(cs)
            missing = 0
            step = Decimal("0.25")
            s = Decimal("0")
            while s <= smax:
                c = Decimal("0")
                while c <= cmax:
                    if (s.quantize(CENTS), c.quantize(CENTS)) not in b.grid and limitation_ok(b, s, c):
                        missing += 1
                    c += step
                s += step
            if missing:
                result.problems.append(Problem(
                    "warning", b.sheet, f"A{b.source_row}",
                    f"{missing} power(s) inside the Limitation have no price (N) — possibly a missing price ({b.label()})"))
