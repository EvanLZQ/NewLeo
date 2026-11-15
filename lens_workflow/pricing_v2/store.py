"""Load the ACTIVE price version from the database as an engine.Catalog.

The catalog is cached per process and keyed by (version id, version
updated_at, lens-line state), so activating another version or editing a
lens line is picked up on the next request by every worker."""
import threading

from django.db.models import Max

from lens_workflow.models import LensLine, PriceBlock, PriceTableVersion

from . import engine as E

_lock = threading.Lock()
_cache = {}


def active_version():
    return PriceTableVersion.objects.filter(status=PriceTableVersion.Status.ACTIVE).first()


def _lines_state():
    agg = LensLine.objects.aggregate(m=Max("updated_at"))
    return (agg["m"], LensLine.objects.count())


def catalog_for(version):
    key = (version.pk, version.updated_at, _lines_state())
    with _lock:
        hit = _cache.get("catalog")
        if hit and hit[0] == key:
            return hit[1]
    lines = [E.Line(code=x.code, display_name=x.display_name, sort_order=x.sort_order,
                    description=x.description)
             for x in LensLine.objects.filter(is_active=True)]
    blocks = [E.block_from_row(r) for r in PriceBlock.objects.filter(version=version).select_related("line")]
    cat = E.Catalog(blocks, lines, version_id=version.pk, version_label=version.label)
    with _lock:
        _cache["catalog"] = (key, cat)
    return cat


def active_catalog():
    """engine.Catalog of the active version, or None when no v2 version is
    active (then the legacy pricing in lens_workflow/pricing.py applies)."""
    v = active_version()
    return catalog_for(v) if v is not None else None


def clear_cache():
    with _lock:
        _cache.clear()
