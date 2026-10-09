"""
Pure helpers for the public order-tracking page (Order/views.py trackOrder).
Kept free of model/DB imports on purpose so the carrier matching and
timeline logic can be unit-tested without a database.
"""
import re
from urllib.parse import quote

# ── Carrier tracking links ───────────────────────────────────────────────────
# OrderInfo.shipping_company is free text typed by staff in the admin, so
# links are picked by recognising the name, not by a fixed list. Staff
# should type one of: DHL, FedEx, UPS, USPS, SF International / SF Express /
# 顺丰国际. Anything else (or a carrier we can't recognise) falls through to
# 17TRACK, a universal multi-carrier lookup.
#
# NOTE: the SF Express URL pattern below could not be confirmed against a
# real waybill when this was written — check it with a real SF number
# before relying on it; the tracking number is always shown (and
# copyable) next to the link regardless.
_CARRIER_LINKS = [
    (re.compile(r"\bdhl\b", re.I),
     "https://www.dhl.com/global-en/home/tracking.html?tracking-id={n}"),
    (re.compile(r"fed\s*ex", re.I),
     "https://www.fedex.com/fedextrack/?trknbr={n}"),
    (re.compile(r"\busps\b", re.I),
     "https://tools.usps.com/go/TrackConfirmAction?tLabels={n}"),
    (re.compile(r"\bups\b", re.I),
     "https://www.ups.com/track?tracknum={n}"),
    (re.compile(r"\bsf\b|sf[\s-]*(express|international)|顺丰", re.I),
     "https://www.sf-express.com/chn/en/dynamic_function/waybill/#search/bill-number/{n}"),
]
_FALLBACK_LINK = "https://t.17track.net/en#nums={n}"


def carrier_tracking_url(carrier, tracking_number):
    number = (tracking_number or "").strip()
    if not number:
        return None
    name = (carrier or "").strip()
    encoded = quote(number, safe="")
    for pattern, template in _CARRIER_LINKS:
        if pattern.search(name):
            return template.format(n=encoded)
    return _FALLBACK_LINK.format(n=encoded)


# ── Status + timeline ────────────────────────────────────────────────────────
STATUS_LABELS = {
    "PROCESSING": "Processing",
    "SHIPPED": "Shipped",
    "DELIVERED": "Delivered",
    "COMPLETE": "Delivered",
    "CANCELED": "Canceled",
    "REFUND": "Refunded",
}

# (key, label) — the four stages shown as a progress bar.
STEPS = [
    ("placed", "Order placed"),
    ("processing", "Processing"),
    ("shipped", "Shipped"),
    ("delivered", "Delivered"),
]
# How far along each ordinary status is (index into STEPS).
_PROGRESS = {"PROCESSING": 1, "SHIPPED": 2, "DELIVERED": 3, "COMPLETE": 3}
_TERMINAL = {"CANCELED", "REFUND"}


def build_timeline(order_status, created_at, events):
    """
    events: iterable of (status, datetime) in chronological order, from
    OrderStatusEvent. Orders that predate that table have no events, so
    their steps still show the right progress, just without dates (except
    "Order placed", which always has OrderInfo.created_at).
    """
    events = list(events or [])

    def last_date(*statuses):
        for status, at in reversed(events):
            if status in statuses:
                return at
        return None

    terminal = order_status if order_status in _TERMINAL else None
    progress = _PROGRESS.get(order_status, 1)

    dates = {
        "placed": created_at,
        "processing": None,
        "shipped": last_date("SHIPPED"),
        "delivered": last_date("DELIVERED", "COMPLETE"),
    }

    steps = []
    for index, (key, label) in enumerate(STEPS):
        if index == 0:
            state = "done"
        elif terminal:
            state = "pending"
        elif index < progress or (index == progress == len(STEPS) - 1):
            state = "done"
        elif index == progress:
            state = "current"
        else:
            state = "pending"
        steps.append({"key": key, "label": label, "state": state, "date": dates[key]})

    return {
        "steps": steps,
        "terminal": terminal,
        "terminal_date": last_date(*_TERMINAL) if terminal else None,
    }
