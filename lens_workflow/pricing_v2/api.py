"""Storefront endpoints for lens pricing v2 (all under /api/lens-workflow/v2/).

    GET  config/        categories, ADD / reader ranges, labels, swatches, lines
    POST selections/    every lens choice that at least one line can make for
                        this prescription (drives the Lens Type / tint / colour /
                        depth / coating steps — §3.4)
    POST quote/         line cards for one full choice (§1.3–1.4)
    POST reader-quote/  the Readers price buttons for one power (§1.6)

Prices here are informative; checkout re-prices server-side
(lens_workflow.pricing_v2.cart) and ignores any client price.
"""
from decimal import Decimal, InvalidOperation

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from . import config as C
from . import engine as E
from . import store
from .cart import check_add


def _err(msg, code=status.HTTP_400_BAD_REQUEST):
    return Response({"detail": msg}, status=code)


def _num(v, name):
    if v in (None, ""):
        return Decimal("0")
    try:
        return Decimal(str(v))
    except (InvalidOperation, ValueError):
        raise E.SelectionError(f"{name} must be a number")


def _eye(d, side):
    d = d or {}
    axis = d.get("axis")
    try:
        axis = int(Decimal(str(axis))) if axis not in (None, "") else None
    except (InvalidOperation, ValueError):
        raise E.SelectionError(f"{side}.axis must be a number")
    return E.EyeRx(_num(d.get("sph"), f"{side}.sph"), _num(d.get("cyl"), f"{side}.cyl"), axis), \
        _num(d.get("add"), f"{side}.add")


def _rx(data, cfg):
    cat = data.get("category")
    if cat not in (E.SV, E.BIFOCAL, E.PROGRESSIVE, E.NON_RX):
        raise E.SelectionError("category must be SINGLE_VISION, BIFOCAL, PROGRESSIVE or NON_RX")
    if cat == E.NON_RX:
        return cat, E.EyeRx(), E.EyeRx()
    if not data.get("od") or not data.get("os"):
        raise E.SelectionError("od and os are required")
    od, add_r = _eye(data["od"], "od")
    os_, add_l = _eye(data["os"], "os")
    bad = check_add(cfg, cat, add_r, add_l)
    if bad:
        raise E.SelectionError(bad)
    return cat, od, os_


def _catalog():
    v = store.active_version()
    return (store.catalog_for(v), v) if v else (None, None)


def _swatch(cfg, sel_tint, color, depth):
    fam = sel_tint
    pattern = cfg["swatches"].get(fam)
    if not pattern:
        return None
    alias = (cfg.get("swatch_color_alias", {}).get(color) or {}).get(fam, color)
    return pattern.format(color=alias, depth=depth or 50)


class ConfigView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        cfg = C.get_config()
        cat, v = _catalog()
        return Response({
            "pricing_active": v is not None,
            "price_version": {"id": v.pk, "label": v.label} if v else None,
            "categories": cfg["categories"],
            "add": {"min": cfg["add_min"], "max": cfg["add_max"], "step": cfg["add_step"],
                    "required_for": cfg["add_required_categories"]},
            "readers": {"min": cfg["reader_min"], "max": cfg["reader_max"], "step": cfg["reader_step"],
                        "powers": [str(p) for p in E.reader_powers(cfg)],
                        "coatings": cfg["reader_coatings"]},
            "max_cyl": cfg["max_cyl"],
            "lens_type_labels": cfg["lens_type_labels"], "tint_labels": cfg["tint_labels"],
            "coating_labels": cfg["coating_labels"], "color_labels": cfg["color_labels"],
            "depths": cfg["depths"],
            "lines": [{"code": x.code, "display_name": x.display_name, "description": x.description}
                      for x in (cat.lines if cat else [])],
        })


class SelectionsView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        cfg = C.get_config()
        catalog, v = _catalog()
        if catalog is None:
            return _err("Lens prices are being updated. Please try again in a few minutes.", 503)
        try:
            cat, od, os_ = _rx(request.data, cfg)
        except E.SelectionError as exc:
            return _err(str(exc))
        eyes = E.make_eyes(cat, od, os_)
        blocked = cat != E.NON_RX and E.over_max_cyl(cfg, od, os_)
        found = {} if blocked else E.available_selections(catalog, cfg, cat, od, os_)
        rows = []
        for sel, lines in sorted(found.items(), key=lambda kv: (
                kv[0].lens_type, kv[0].tint, kv[0].color, kv[0].depth or 0, kv[0].coating)):
            d = sel.as_dict()
            d["lines"] = lines
            if sel.color:
                fam = sel.tint if sel.lens_type == "SUN" else "PHOTOCHROMIC"
                d["swatch"] = _swatch(cfg, fam, sel.color, sel.depth)
            rows.append(d)
        reason = None
        if blocked:
            reason = E.REASON_MAX_CYL.format(max_cyl=cfg["max_cyl"])
        elif not rows:
            reason = E.REASON_NO_RX
        return Response({"price_version": v.pk, "category": cat,
                         "pricing_rx": {k: e.as_dict() for k, e in eyes.items()},
                         "selections": rows, "unavailable_reason": reason})


class QuoteView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        cfg = C.get_config()
        catalog, v = _catalog()
        if catalog is None:
            return _err("Lens prices are being updated. Please try again in a few minutes.", 503)
        try:
            cat, od, os_ = _rx(request.data, cfg)
            s = request.data.get("selection") or {}
            depth = s.get("depth")
            sel = E.Selection(lens_type=s.get("lens_type") or "", tint=s.get("tint") or "",
                              color=s.get("color") or "",
                              depth=int(depth) if depth not in (None, "") else None,
                              coating=s.get("coating") or "N")
            q = E.quote(catalog, cfg, cat, od, os_, sel)
        except (E.SelectionError, ValueError) as exc:
            return _err(str(exc))
        out = q.as_dict()
        out["price_version"] = v.pk
        return Response(out)


class ReaderQuoteView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        cfg = C.get_config()
        catalog, v = _catalog()
        if catalog is None:
            return _err("Lens prices are being updated. Please try again in a few minutes.", 503)
        try:
            opts = E.quote_reader(catalog, cfg, _num(request.data.get("power"), "power"))
        except E.SelectionError as exc:
            return _err(str(exc))
        return Response({
            "price_version": v.pk, "power": str(E.Q(request.data.get("power"))),
            "options": [{"coating": o["coating"], "label": o["label"], "price": str(o["price"]),
                         "line": o["line"]} for o in opts],
        })
