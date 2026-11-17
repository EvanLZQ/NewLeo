"""Versioned import of the lens price file.

    dry_run(path, overrides)            check + report, nothing saved
    import_file(path, overrides, ...)   save as a DRAFT version (+ report)
    activate(version)                   DRAFT/ARCHIVED → ACTIVE, old ACTIVE → ARCHIVED
    rollback()                          re-activate the previously active version

Nothing is ever deleted: old versions stay ARCHIVED and orders keep a
foreign key to the version they were priced with.

The report contains every error / warning with its cell, a summary, and the
price-change list against the currently active version (per product and
per cell) so the boss can approve a re-priced file before it goes live.
"""
import csv
import hashlib
import io
import json
from collections import Counter, defaultdict
from decimal import Decimal

import yaml
from django.db import transaction
from django.utils import timezone

from lens_workflow.models import LensLine, PriceBlock, PriceTableVersion

from . import config as C
from . import engine as E
from . import sheet as S
from . import store


class ImportRefused(Exception):
    def __init__(self, result, report):
        super().__init__(f"{len(result.errors)} error(s); nothing was saved")
        self.result = result
        self.report = report


def load_overrides(path):
    if not path:
        return []
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    items = data.get("overrides", data) if isinstance(data, dict) else data
    return list(items or [])


def sheet_map():
    return {x.sheet_name.strip().lower(): x.code for x in LensLine.objects.all()}


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def parse_bytes(data, overrides):
    return S.parse_workbook(io.BytesIO(data), sheet_map(), C.get_config(), overrides)


# ── diff ─────────────────────────────────────────────────────────────────────

def _key(line, rx, lens, color, depths_key, coating, index):
    return (line, rx, lens, color, depths_key or "", coating, f"{Decimal(index):.2f}")


def _key_label(k):
    line, rx, lens, color, depths, coating, index = k
    return f"{line} | {rx} | {lens} | {color or 'n'} | {depths or '-'} | {coating} | {index}"


def _parsed_map(result):
    out = {}
    for b in result.blocks:
        out[_key(b.line, b.rx_type, b.lens_type, b.color_group, b.depths_key, b.coating, b.lens_index)] = (
            {f"{s}|{c}": p for (s, c), p in b.grid.items()},
            [r.raw for r in b.rows], f"{b.sheet}!{b.source_row}")
    return out


def _db_map(version):
    out = {}
    if version is None:
        return out
    for r in PriceBlock.objects.filter(version=version).select_related("line"):
        out[_key(r.line.code, r.rx_type, r.lens_type, r.color_group, r.depths_key, r.coating, r.lens_index)] = (
            {k: Decimal(v) for k, v in r.grid.items()}, [d.get("raw") for d in r.rows], f"{r.sheet}!{r.source_row}")
    return out


def diff(old, new):
    """old/new: {key: (grid, rows_raw, where)} → dict with products added /
    removed / changed and the cell-level change list."""
    products, cells = [], []
    for k in sorted(set(old) | set(new)):
        o, n = old.get(k), new.get(k)
        if o is None:
            products.append({"product": _key_label(k), "change": "added", "where": n[2], "cells": len(n[0])})
            continue
        if n is None:
            products.append({"product": _key_label(k), "change": "removed", "where": o[2], "cells": len(o[0])})
            continue
        og, ng = o[0], n[0]
        changed = []
        for cell in sorted(set(og) | set(ng)):
            a, b = og.get(cell), ng.get(cell)
            if a != b:
                changed.append((cell, a, b))
        rows_changed = o[1] != n[1]
        if not changed and not rows_changed:
            continue
        ups = [b - a for _, a, b in changed if a is not None and b is not None]
        products.append({
            "product": _key_label(k), "change": "changed", "where": n[2],
            "cells_changed": len(changed),
            "cells_now_priced": sum(1 for _, a, b in changed if a is None),
            "cells_now_N": sum(1 for _, a, b in changed if b is None),
            "old_prices": sorted({str(a) for _, a, _ in changed if a is not None}),
            "new_prices": sorted({str(b) for _, _, b in changed if b is not None}),
            "max_increase": str(max(ups)) if ups and max(ups) > 0 else None,
            "max_decrease": str(min(ups)) if ups and min(ups) < 0 else None,
            "limitation_or_label_changed": rows_changed,
            "old_rows": o[1] if rows_changed else None, "new_rows": n[1] if rows_changed else None,
        })
        for cell, a, b in changed:
            s, c = cell.split("|")
            cells.append({"product": _key_label(k), "sphere": s, "cylinder": c,
                          "old": str(a) if a is not None else "N", "new": str(b) if b is not None else "N"})
    counts = Counter(p["change"] for p in products)
    return {"summary": dict(counts), "products": products, "cells": cells}


# ── report ───────────────────────────────────────────────────────────────────

def build_report(result, filename, sha, overrides, against):
    by_line = defaultdict(lambda: {"blocks": 0, "priced_cells": 0})
    for b in result.blocks:
        by_line[b.line]["blocks"] += 1
        by_line[b.line]["priced_cells"] += len(b.grid)
    warn_kinds = Counter(w.message.split(":")[0].split("(")[0].strip()[:80] for w in result.warnings)
    d = diff(_db_map(against), _parsed_map(result)) if result.ok else None
    return {
        "file": filename, "sha256": sha, "created": timezone.now().isoformat(),
        "ok": result.ok, "sheets": result.sheets,
        "lines": dict(by_line), "blocks": len(result.blocks),
        "errors": [p.as_dict() for p in result.errors],
        "warnings": [p.as_dict() for p in result.warnings],
        "warning_kinds": dict(warn_kinds),
        "overrides": overrides, "overrides_applied": result.overrides_applied,
        "compared_with": {"version": against.pk, "label": against.label} if against else None,
        "diff": d,
    }


def write_report(report, outdir):
    """report.json, problems.csv, price_changes_products.csv,
    price_changes_cells.csv and a short summary.md in `outdir`."""
    import os
    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, "report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1, default=str)
    with open(os.path.join(outdir, "problems.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["level", "sheet", "cell", "message"])
        for p in report["errors"] + report["warnings"]:
            w.writerow([p["level"], p["sheet"], p["cell"], p["message"]])
    d = report.get("diff") or {"products": [], "cells": [], "summary": {}}
    with open(os.path.join(outdir, "price_changes_products.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["product (line | rx | lens | color | depth | coating | index)", "change", "where",
                    "cells changed", "now priced", "now N", "old prices", "new prices",
                    "max increase", "max decrease", "limitation/label changed"])
        for p in d["products"]:
            w.writerow([p["product"], p["change"], p.get("where"), p.get("cells_changed", p.get("cells")),
                        p.get("cells_now_priced", ""), p.get("cells_now_N", ""),
                        " ".join(p.get("old_prices", []) or []), " ".join(p.get("new_prices", []) or []),
                        p.get("max_increase") or "", p.get("max_decrease") or "",
                        "yes" if p.get("limitation_or_label_changed") else ""])
    with open(os.path.join(outdir, "price_changes_cells.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["product", "|sphere|", "|cylinder|", "old", "new"])
        for c in d["cells"]:
            w.writerow([c["product"], c["sphere"], c["cylinder"], c["old"], c["new"]])
    lines = [f"# Lens price import report: {report['file']}", "",
             f"- ok: {report['ok']}  blocks: {report['blocks']}  errors: {len(report['errors'])}  "
             f"warnings: {len(report['warnings'])}",
             f"- compared with: {report['compared_with']}", f"- diff: {d.get('summary')}", ""]
    for p in report["errors"][:200]:
        lines.append(f"- ERROR {p['sheet']}!{p['cell']}: {p['message']}")
    lines.append("")
    lines.append("## Warning kinds")
    for k, v in report["warning_kinds"].items():
        lines.append(f"- {v} × {k}")
    with open(os.path.join(outdir, "summary.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


# ── actions ──────────────────────────────────────────────────────────────────

def dry_run(data, filename, overrides):
    result = parse_bytes(data, overrides)
    return result, build_report(result, filename, _sha(data), overrides, store.active_version())


@transaction.atomic
def import_file(data, filename, overrides, *, label="", user="", notes=""):
    """Save the file as a new DRAFT version. Raises ImportRefused on errors."""
    result, report = dry_run(data, filename, overrides)
    if not result.ok:
        raise ImportRefused(result, report)
    lines = {x.code: x for x in LensLine.objects.all()}
    version = PriceTableVersion.objects.create(
        label=(label or filename)[:200], source_filename=filename[:255], file_sha256=report["sha256"],
        overrides=overrides, status=PriceTableVersion.Status.DRAFT, imported_by=user[:150],
        report=report, notes=notes)
    rows = []
    for b in result.blocks:
        rows.append(PriceBlock(
            version=version, line=lines[b.line], sheet=b.sheet[:100], source_row=b.source_row,
            position=b.position, rx_type=b.rx_type, lens_type=b.lens_type, color_group=b.color_group[:100],
            colors=b.colors, is_generic_color=b.is_generic_color, depths=b.depths, depths_key=b.depths_key,
            coating=b.coating, lens_index=b.lens_index, material=b.material[:150], rationale=b.rationale,
            notes=b.notes, raw=b.raw, rows=[r.as_dict() for r in b.rows], grid=b.grid_json()))
    PriceBlock.objects.bulk_create(rows, batch_size=200)
    return version, report


@transaction.atomic
def activate(version, user=""):
    version = PriceTableVersion.objects.select_for_update().get(pk=version.pk if hasattr(version, "pk") else version)
    if version.status == PriceTableVersion.Status.ACTIVE:
        return version
    if not version.blocks.exists():
        raise ValueError(f"version {version.pk} has no blocks")
    PriceTableVersion.objects.select_for_update().filter(
        status=PriceTableVersion.Status.ACTIVE).update(
        status=PriceTableVersion.Status.ARCHIVED, updated_at=timezone.now())
    version.status = PriceTableVersion.Status.ACTIVE
    version.activated_at = timezone.now()
    version.activated_by = user[:150]
    version.save()
    store.clear_cache()
    return version


def rollback(user=""):
    """Activate the version that was active before the current one."""
    current = store.active_version()
    qs = PriceTableVersion.objects.filter(activated_at__isnull=False).exclude(
        status=PriceTableVersion.Status.ACTIVE)
    if current is not None:
        qs = qs.filter(activated_at__lt=current.activated_at)
    previous = qs.order_by("-activated_at").first()
    if previous is None:
        raise ValueError("no earlier active version to roll back to")
    return activate(previous, user=user)
