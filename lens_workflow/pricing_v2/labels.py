"""Human-readable labels for a CompleteSet.lens_selection (cart, order
pages, admin, e-mails). The cart serializer used to show the labels of the
legacy step rows in these same keys, so the storefront needs no change."""
from . import config as C


def selection_labels(sel, cfg=None):
    cfg = cfg or C.get_config()
    cats = {c["code"]: c for c in cfg["categories"]}
    cat = cats.get(sel.get("category"), {})
    out = {
        "lens_type": cat.get("label", sel.get("category")),
        "is_prescription_required": bool(cat.get("rx_required", True)),
        "function_path": None, "tint_type": None, "color_option": None,
        "index_option": None, "reader_strength": None, "coatings": [],
    }
    bits = [out["lens_type"]]
    if sel.get("category") == "READERS":
        out["reader_strength"] = f"+{sel.get('power')}"
        coat = next((c["label"] for c in cfg["reader_coatings"] if c["code"] == sel.get("coating")),
                    sel.get("coating"))
        out["function_path"] = coat
        bits += [out["reader_strength"], coat]
    else:
        out["function_path"] = cfg["lens_type_labels"].get(sel.get("lens_type"), sel.get("lens_type"))
        bits.append(out["function_path"])
        if sel.get("tint"):
            out["tint_type"] = cfg["tint_labels"].get(sel["tint"], sel["tint"])
            bits.append(out["tint_type"])
        if sel.get("color"):
            color = cfg["color_labels"].get(sel["color"], sel["color"])
            if sel.get("depth"):
                color = f"{sel['depth']}% {color}"
            out["color_option"] = color
            bits.append(color)
        if sel.get("coating") == "BLUE":
            out["coatings"] = [cfg["coating_labels"]["BLUE"]]
            bits.append(out["coatings"][0])
        line = sel.get("line")
        if line:
            from lens_workflow.models import LensLine
            ln = LensLine.objects.filter(code=line).first()
            out["index_option"] = f"{ln.display_name if ln else line} {sel.get('index')}"
            bits.append(out["index_option"])
    out["summary"] = " / ".join(str(b) for b in bits if b)
    return out
