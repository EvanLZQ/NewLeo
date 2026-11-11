"""Test helper: create a typed prescription the way the lens page does.

Since the 2026-11-11 ownership fix a guest Rx is only usable by the browser
session that typed it, so tests that drive the API as a shopper must create
the Rx through that same client (not with a bare ORM row, which is now an
unbound legacy row nobody but staff can use by id).
"""
from .models import PrescriptionInfo


def rx_via_api(client, **fields):
    body = {key: (str(value) if value is not None else None) for key, value in fields.items()}
    res = client.post("/api/prescriptions/", body, format="json")
    assert res.status_code == 201, res.content
    return PrescriptionInfo.objects.get(id=res.data["id"])
