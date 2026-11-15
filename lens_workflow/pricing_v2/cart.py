"""Price a CompleteSet (cart item / order line) made by the v2 lens flow.

`CompleteSet.lens_selection` holds the customer's choice; this module turns
it into the lens price with the ACTIVE price version (boss Q15=A: an open
cart is re-priced at checkout), and fills the snapshot fields
(price_version, lens_line, pricing_rx, price_snapshot) that `save()` stores.

A pair on a paid order is never re-priced: its snapshot is returned as is,
so a later price file cannot change an old order.
"""
from decimal import Decimal

from django.utils import timezone

from . import config as C
from . import engine as E
from . import store


class LensUnavailable(Exception):
    def __init__(self, message):
        super().__init__(message)
        self.message = message


REASON_NO_TABLE = "Lens prices are being updated. Please try again in a few minutes."
REASON_NEED_RX = "A prescription is required to price this lens"
REASON_ADD = "ADD must be between +{lo} and +{hi} for bifocal and progressive lenses"
REASON_GONE = "This lens option is no longer available for this prescription. Please choose your lenses again."


def is_v2(complete_set):
    return bool(getattr(complete_set, "lens_selection", None))


def _d(v):
    return Decimal(str(v)) if v not in (None, "") else Decimal("0")


def selection_from_json(data):
    """lens_selection JSON → (category, engine.Selection | None, extra). Raises E.SelectionError."""
    if not isinstance(data, dict):
        raise E.SelectionError("lens_selection must be an object")
    cat = data.get("category")
    if cat not in E.CATEGORIES:
        raise E.SelectionError(f"category must be one of {', '.join(E.CATEGORIES)}")
    if cat == E.READERS:
        if data.get("power") in (None, ""):
            raise E.SelectionError("power is required for READERS")
        if not data.get("coating"):
            raise E.SelectionError("coating is required for READERS")
        return cat, None, {"power": E.Q(data["power"]), "coating": data["coating"]}
    depth = data.get("depth")
    sel = E.Selection(
        lens_type=data.get("lens_type") or "", tint=data.get("tint") or "",
        color=data.get("color") or "", depth=int(depth) if depth not in (None, "") else None,
        coating=data.get("coating") or "N")
    E.validate_selection(sel)
    if not data.get("line") or data.get("index") in (None, ""):
        raise E.SelectionError("line and index are required")
    return cat, sel, {"line": data["line"], "index": E.Q(data["index"])}


def eyes_from_prescription(rx):
    od = E.EyeRx(_d(rx.sphere_r), _d(rx.cylinder_r), int(rx.axis_r) if rx.axis_r is not None else None)
    os_ = E.EyeRx(_d(rx.sphere_l), _d(rx.cylinder_l), int(rx.axis_l) if rx.axis_l is not None else None)
    return od, os_


def check_add(cfg, category, add_r, add_l):
    if category not in cfg.get("add_required_categories", []):
        return None
    lo, hi, step = Decimal(cfg["add_min"]), Decimal(cfg["add_max"]), Decimal(cfg["add_step"])
    for v in (add_r, add_l):
        v = _d(v)
        if v < lo or v > hi or ((v - lo) % step) != 0:
            return REASON_ADD.format(lo=cfg["add_min"], hi=cfg["add_max"])
    return None


def _frozen(complete_set):
    order = getattr(complete_set, "order", None) if complete_set.order_id else None
    return bool(order is not None and getattr(order, "payment_status", "UNPAID") != "UNPAID"
                and complete_set.price_snapshot)


def price(complete_set):
    """→ dict(lens_price, prism_price, items, snapshot fields). Raises LensUnavailable."""
    if _frozen(complete_set):
        snap = complete_set.price_snapshot
        return {"lens_price": Decimal(snap["unit_price"]), "frozen": True, "snapshot": snap,
                "items": snap.get("items") or []}
    try:
        category, sel, extra = selection_from_json(complete_set.lens_selection)
    except (E.SelectionError, ValueError, TypeError) as exc:
        raise LensUnavailable(f"Invalid lens selection: {exc}")
    version = store.active_version()
    if version is None:
        raise LensUnavailable(REASON_NO_TABLE)
    catalog = store.catalog_for(version)
    cfg = C.get_config()
    rx = complete_set.prescription if complete_set.prescription_id else None

    if category == E.READERS:
        try:
            opts = E.quote_reader(catalog, cfg, extra["power"])
        except E.SelectionError as exc:
            raise LensUnavailable(str(exc))
        hit = next((o for o in opts if o["coating"] == extra["coating"]), None)
        if hit is None:
            raise LensUnavailable(REASON_GONE)
        unit = hit["price"]
        label = f"Readers +{extra['power']} / {hit['label']}"
        snapshot = {"category": category, "line": hit["line"], "index": str(hit["index"]),
                    "charged_index": str(hit["charged_index"]), "unit_price": str(unit),
                    "blocks": [hit["block"]], "power": str(extra["power"]), "coating": hit["coating"]}
        pricing_rx = {"reader_power": str(extra["power"]), "table": cfg.get("reader_rx_type")}
        line_code = hit["line"]
    else:
        if category != E.NON_RX:
            if rx is None:
                raise LensUnavailable(REASON_NEED_RX)
            bad_add = check_add(cfg, category, rx.add_r, rx.add_l)
            if bad_add:
                raise LensUnavailable(bad_add)
            od, os_ = eyes_from_prescription(rx)
        else:
            od, os_ = E.EyeRx(), E.EyeRx()
        q = E.quote(catalog, cfg, category, od, os_, sel)
        if q.blocked_reason:
            raise LensUnavailable(q.blocked_reason)
        card = q.card(extra["line"])
        opt = card.option(extra["index"]) if card else None
        if opt is None:
            raise LensUnavailable(REASON_GONE if q.cards else E.REASON_NO_RX)
        unit = opt.price
        bits = [card.display_name, f"index {opt.index}"]
        bits.append(cfg["lens_type_labels"].get(sel.lens_type, sel.lens_type))
        if sel.tint:
            bits.append(cfg["tint_labels"].get(sel.tint, sel.tint))
        if sel.color:
            bits.append(cfg["color_labels"].get(sel.color, sel.color))
        if sel.depth:
            bits.append(f"{sel.depth}%")
        if sel.coating == "BLUE":
            bits.append(cfg["coating_labels"]["BLUE"])
        if opt.free_upgrade:
            bits.append(f"free upgrade from {opt.charged_index}")
        label = " / ".join(bits)
        snapshot = {"category": category, "line": card.line, "index": str(opt.index),
                    "charged_index": str(opt.charged_index), "free_upgrade": opt.free_upgrade,
                    "unit_price": str(unit), "blocks": opt.blocks,
                    "eye_prices": {k: str(v) for k, v in opt.eye_prices.items()},
                    "recommended_index": str(card.recommended_index),
                    "selection": sel.as_dict(), "material": opt.material}
        pricing_rx = {k: v.as_dict() for k, v in q.eyes.items()}
        line_code = card.line

    items = [{"component": "lens", "label": label, "price": float(unit), "tier": line_code,
              "lens_index": snapshot["index"], "free_upgrade": bool(snapshot.get("free_upgrade"))}]
    snapshot.update({"version_id": version.pk, "version_label": version.label,
                     "computed_at": timezone.now().isoformat(), "items": items})
    return {"lens_price": unit, "frozen": False, "snapshot": snapshot, "items": items,
            "version": version, "line": line_code, "pricing_rx": pricing_rx}


def apply_snapshot(complete_set, result):
    """Copy the pricing result onto the instance (saved by the caller)."""
    if result.get("frozen"):
        return
    complete_set.price_version = result["version"]
    complete_set.lens_line = result["line"]
    complete_set.pricing_rx = result["pricing_rx"]
    complete_set.price_snapshot = result["snapshot"]
