"""Security regression: typed-prescription (and related) enumeration.

Acceptance follow-up to the cart fix (2026-11-11): /api/prescriptions/<id>
and /api/prescriptions/batch let anyone read, edit and delete every guest
prescription (customer NULL) by counting up the sequential ids; the lens
workflow quote endpoints would price/recommend from anyone's Rx id; a guest
Rx could be attached to an attacker's own cart item and read back; and the
wish-list endpoints took any id with no check.

Ownership now follows Order/ownership.py: the signed-in owner, the same
signed-out session, or staff. Everything else answers 404 (the same as an id
that does not exist), and the victim's row is left untouched.
"""
import json
import shutil
import tempfile
from decimal import Decimal as D

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from Customer.models import WishList
from General.models import Address
from Order.models import CompleteSet, OrderInfo
from Order.tests import _address_fields, _frame
from Prescription.models import PrescriptionInfo
from Prescription.testing import rx_via_api

User = get_user_model()

PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
RX = dict(sphere_r="-2.00", sphere_l="-2.25", cylinder_r="-0.50", cylinder_l="0",
          axis_r="90", pd_r="31.5", pd_l="31.5", nickname="victim-rx")


def _client():
    c = APIClient(enforce_csrf_checks=False)
    c.defaults["HTTP_X_FORWARDED_PROTO"] = "https"
    return c


class _Base(TestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self._private = tempfile.mkdtemp(prefix="rx-own-private-")
        self._media = tempfile.mkdtemp(prefix="rx-own-media-")
        self._override = override_settings(PRIVATE_MEDIA_ROOT=self._private,
                                           MEDIA_ROOT=self._media)
        self._override.enable()
        self.frame = _frame("RX-OWN-1", "20.00")

    def tearDown(self):
        self._override.disable()
        shutil.rmtree(self._private, ignore_errors=True)
        shutil.rmtree(self._media, ignore_errors=True)

    def _user(self, name, **extra):
        return User.objects.create_user(username=name, email=f"{name}@example.com",
                                        password="pw-123456", **extra)

    def _signed_in(self, user):
        c = _client()
        c.force_login(user)
        return c

    def _attackers(self):
        """Fresh anonymous visitor, a different guest session that has its
        own Rx, and a different signed-in account."""
        other_guest = _client()
        rx_via_api(other_guest, sphere_r="-1.00")
        return {
            "anonymous": _client(),
            "other guest session": other_guest,
            "other signed-in user": self._signed_in(self._user("eve")),
        }

    def _assert_rx_hidden(self, client, rx_id, label):
        before = PrescriptionInfo.objects.filter(id=rx_id).values().first()
        for method, data in (("get", None), ("patch", {"sphere_r": "-9.00"}), ("delete", None)):
            res = getattr(client, method)(f"/api/prescriptions/{rx_id}", data, format="json")
            self.assertEqual(res.status_code, 404, f"{label} {method}: {res.content}")
            self.assertEqual(res.data, {"error": "Not found"}, label)
        res = client.post("/api/prescriptions/batch", {"ids": [rx_id]}, format="json")
        self.assertEqual(res.status_code, 200, label)
        self.assertEqual(res.data, [], f"{label} batch leaked {res.data}")
        # Untouched: not edited, not deleted.
        self.assertEqual(PrescriptionInfo.objects.filter(id=rx_id).values().first(), before, label)

    def _assert_rx_visible(self, client, rx_id, label):
        res = client.get(f"/api/prescriptions/{rx_id}")
        self.assertEqual(res.status_code, 200, f"{label}: {res.content}")
        self.assertEqual(res.data["id"], rx_id)
        self.assertNotIn("guest_token", res.data)
        res = client.post("/api/prescriptions/batch", {"ids": [rx_id]}, format="json")
        self.assertEqual([r["id"] for r in res.data], [rx_id], label)


class GuestPrescriptionEnumerationTests(_Base):
    def setUp(self):
        super().setUp()
        self.victim = _client()
        self.rx = rx_via_api(self.victim, **RX)

    def test_guest_rx_is_bound_to_the_session_token(self):
        self.assertIsNone(self.rx.customer_id)
        self.assertTrue(self.rx.guest_token)
        self.assertEqual(self.victim.session["cart_owner_token"], self.rx.guest_token)
        res = self.victim.post("/api/prescriptions/", RX, format="json")
        self.assertNotIn("guest_token", json.dumps(res.data))

    def test_attackers_get_404_on_get_patch_delete_and_empty_batch(self):
        for label, attacker in self._attackers().items():
            self._assert_rx_hidden(attacker, self.rx.id, label)

    def test_counting_ids_finds_nothing(self):
        attacker = _client()
        res = attacker.post("/api/prescriptions/batch",
                            {"ids": list(range(1, self.rx.id + 50))}, format="json")
        self.assertEqual(res.data, [])
        for rx_id in range(1, self.rx.id + 3):
            self.assertEqual(attacker.get(f"/api/prescriptions/{rx_id}").status_code, 404)

    def test_missing_id_looks_the_same_as_unowned(self):
        attacker = _client()
        missing = attacker.get(f"/api/prescriptions/{self.rx.id + 1000}")
        unowned = attacker.get(f"/api/prescriptions/{self.rx.id}")
        self.assertEqual((missing.status_code, missing.data), (unowned.status_code, unowned.data))

    def test_owner_guest_session_gets_200(self):
        self._assert_rx_visible(self.victim, self.rx.id, "owner guest")
        res = self.victim.patch(f"/api/prescriptions/{self.rx.id}",
                                {"nickname": "mine"}, format="json")
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.data["nickname"], "mine")
        self.assertEqual(self.victim.delete(f"/api/prescriptions/{self.rx.id}").status_code, 204)
        self.assertFalse(PrescriptionInfo.objects.filter(id=self.rx.id).exists())

    def test_owner_keeps_access_after_signing_in_in_the_same_session(self):
        user = self._user("victim")
        self.victim.force_login(user)
        self._assert_rx_visible(self.victim, self.rx.id, "guest then signed in")

    def test_staff_may_access(self):
        staff = self._signed_in(self._user("staffer", is_staff=True))
        self._assert_rx_visible(staff, self.rx.id, "staff")

    def test_attacker_cannot_attach_victim_rx_to_own_cart_item(self):
        for label, attacker in self._attackers().items():
            res = attacker.post("/api/order/createcompleteset", {
                "frame": {"sku": self.frame.sku}, "prescription": {"id": self.rx.id},
            }, format="json")
            self.assertEqual(res.status_code, 400, f"{label}: {res.content}")
            self.assertNotIn("-2.25", json.dumps(res.data))
            # Nor via update of an item the attacker does own.
            own = attacker.post("/api/order/createcompleteset",
                                {"frame": {"sku": self.frame.sku}}, format="json")
            self.assertEqual(own.status_code, 201, own.content)
            res = attacker.patch(f"/api/order/updatecompleteset/{own.data['id']}",
                                 {"prescription": {"id": self.rx.id}}, format="json")
            self.assertEqual(res.status_code, 400, f"{label}: {res.content}")
            self.assertIsNone(CompleteSet.objects.get(id=own.data["id"]).prescription_id)

    def test_lens_workflow_quote_ignores_someone_elses_rx(self):
        """summary / rx-quote must answer exactly as for an id that does not
        exist, so they can't confirm ids or leak powers via the price."""
        attacker = _client()
        for url, method, payload in (
            ("/api/lens-workflow/rx-quote/", "post", lambda rx_id: {"prescription_id": rx_id}),
            ("/api/lens-workflow/summary/", "get", lambda rx_id: {"prescription_id": rx_id}),
        ):
            unowned = getattr(attacker, method)(url, payload(self.rx.id), format="json") \
                if method == "post" else attacker.get(url, payload(self.rx.id))
            missing = getattr(attacker, method)(url, payload(self.rx.id + 1000), format="json") \
                if method == "post" else attacker.get(url, payload(self.rx.id + 1000))
            self.assertEqual(unowned.status_code, missing.status_code, url)
            self.assertEqual(
                json.dumps(unowned.data).replace(str(self.rx.id), "N"),
                json.dumps(missing.data).replace(str(self.rx.id + 1000), "N"), url)


class TypedAndUploadedGuestCartTests(_Base):
    """Victim guest has a cart item with a typed Rx and an uploaded PDF."""

    def setUp(self):
        super().setUp()
        self.victim = _client()
        self.rx = rx_via_api(self.victim, **RX)
        up = self.victim.post("/api/prescriptions/upload", {
            "file": SimpleUploadedFile("victim.pdf", PDF, content_type="application/pdf")},
            format="multipart")
        self.assertEqual(up.status_code, 201, up.content)
        self.upload_id = up.data["id"]
        res = self.victim.post("/api/order/createcompleteset", {
            "frame": {"sku": self.frame.sku}, "prescription": {"id": self.rx.id},
            "prescription_upload": self.upload_id}, format="json")
        self.assertEqual(res.status_code, 201, res.content)
        self.set_id = res.data["id"]
        self.victim.post("/api/order/guest_cart",
                         {"action": "add", "complete_set_id": self.set_id}, format="json")

    def test_attackers_get_404_for_rx_item_and_file(self):
        for label, attacker in self._attackers().items():
            self._assert_rx_hidden(attacker, self.rx.id, label)
            self.assertEqual(attacker.get(f"/api/order/completeset/{self.set_id}").status_code, 404)
            self.assertEqual(attacker.get(
                f"/api/prescriptions/upload/{self.upload_id}/file").status_code, 404)

    def test_owner_sees_rx_item_and_file(self):
        self._assert_rx_visible(self.victim, self.rx.id, "owner")
        self.assertEqual(self.victim.get(f"/api/order/completeset/{self.set_id}").status_code, 200)
        self.assertEqual(self.victim.get(
            f"/api/prescriptions/upload/{self.upload_id}/file").status_code, 200)

    def test_edit_lens_resending_the_same_rx_still_works(self):
        res = self.victim.patch(f"/api/order/updatecompleteset/{self.set_id}", {
            "prescription": {"id": self.rx.id}, "sub_color": "Black"}, format="json")
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.data["prescription"]["id"], self.rx.id)


class SignedInPrescriptionTests(_Base):
    def setUp(self):
        super().setUp()
        self.owner = self._user("owner")
        self.owner_client = self._signed_in(self.owner)
        self.rx = rx_via_api(self.owner_client, **RX)

    def test_signed_in_rx_belongs_to_the_account(self):
        self.assertEqual(self.rx.customer_id, self.owner.pk)
        self.assertEqual(self.rx.guest_token, "")

    def test_owner_gets_200(self):
        self._assert_rx_visible(self.owner_client, self.rx.id, "owner")
        res = self.owner_client.get("/api/prescriptions/")
        self.assertEqual([r["id"] for r in res.data], [self.rx.id])
        res = self.owner_client.patch(f"/api/prescriptions/{self.rx.id}",
                                      {"sphere_r": "-3.00"}, format="json")
        self.assertEqual(res.status_code, 200, res.content)

    def test_attackers_get_404(self):
        for label, attacker in self._attackers().items():
            self._assert_rx_hidden(attacker, self.rx.id, label)
            self.assertNotIn(self.rx.id, [r["id"] for r in
                                          attacker.get("/api/prescriptions/").data])

    def test_staff_may_access(self):
        staff = self._signed_in(self._user("staffer", is_staff=True))
        self._assert_rx_visible(staff, self.rx.id, "staff")


class LegacyUnboundGuestRxTests(_Base):
    """Rows typed before this fix: customer NULL and no guest token."""

    def setUp(self):
        super().setUp()
        self.legacy = PrescriptionInfo.objects.create(sphere_r=D("-4.00"), sphere_l=D("-4.00"))

    def test_default_deny_for_everyone_but_staff(self):
        signed_in = self._signed_in(self._user("someone"))
        for label, client in (("anonymous", _client()), ("signed in", signed_in)):
            self._assert_rx_hidden(client, self.legacy.id, label)
        staff = self._signed_in(self._user("staffer", is_staff=True))
        self._assert_rx_visible(staff, self.legacy.id, "staff")

    def test_owner_of_the_cart_item_it_is_on_can_still_read_it(self):
        owner = self._user("buyer")
        item = CompleteSet.objects.create(frame=self.frame, prescription=self.legacy)
        owner.refresh_from_db()
        owner.shopping_cart.eyeglasses_set.add(item)
        self._assert_rx_visible(self._signed_in(owner), self.legacy.id, "cart owner")
        self._assert_rx_hidden(self._signed_in(self._user("eve")), self.legacy.id, "eve")


class WishListEnumerationTests(_Base):
    def test_guest_wish_list_is_bound_to_the_session(self):
        victim = _client()
        created = victim.post("/api/user/add_wish_list", {}, format="json")
        self.assertEqual(created.status_code, 201, created.content)
        list_id = created.data["id"]
        self.assertEqual(victim.get(f"/api/user/get_wish_list/{list_id}").status_code, 200)
        self.assertEqual(victim.patch(f"/api/user/update_wish_list/{list_id}",
                                      {"product": []}, format="json").status_code, 200)
        for label, attacker in self._attackers().items():
            self.assertEqual(attacker.get(f"/api/user/get_wish_list/{list_id}").status_code,
                             404, label)
            self.assertEqual(attacker.patch(f"/api/user/update_wish_list/{list_id}",
                                            {"product": []}, format="json").status_code, 404, label)
        self.assertTrue(WishList.objects.filter(id=list_id).exists())
        staff = self._signed_in(self._user("staffer", is_staff=True))
        self.assertEqual(staff.get(f"/api/user/get_wish_list/{list_id}").status_code, 200)

    def test_signed_in_owner_and_other_user(self):
        owner = self._user("owner")
        owner.refresh_from_db()
        list_id = owner.wish_list_id
        self.assertEqual(self._signed_in(owner).get(
            f"/api/user/get_wish_list/{list_id}").status_code, 200)
        self.assertEqual(self._signed_in(self._user("eve")).get(
            f"/api/user/get_wish_list/{list_id}").status_code, 404)
        self.assertEqual(_client().get(f"/api/user/get_wish_list/{list_id}").status_code, 404)

    def test_legacy_unbound_guest_list_is_404(self):
        legacy = WishList.objects.create()
        self.assertEqual(_client().get(f"/api/user/get_wish_list/{legacy.id}").status_code, 404)


class AddressAndOrderByIdTests(_Base):
    """Already scoped before this fix; pinned so it stays that way."""

    def setUp(self):
        super().setUp()
        self.owner = self._user("owner")
        self.address = Address.objects.create(customer=self.owner, **_address_fields())
        self.order = OrderInfo.objects.create(
            customer=self.owner, email="owner@example.com", order_number="ELW-T-OWN1",
            order_status="PROCESSING", payment_status="UNPAID", address=self.address,
            sub_total=0, shipping_cost=0, total_amount=0, refound_amount=0, refound_status="", comment="")

    def test_other_user_gets_404_for_address_and_order(self):
        eve = self._signed_in(self._user("eve"))
        self.assertEqual(eve.patch(f"/api/user/update_address/{self.address.id}",
                                   {"city": "pwned"}, format="json").status_code, 404)
        self.assertEqual(eve.delete(f"/api/user/delete_address/{self.address.id}").status_code, 404)
        self.assertEqual(eve.get(f"/api/order/{self.order.id}").status_code, 404)
        self.assertEqual(eve.delete(f"/api/order/cancel_pending/{self.order.id}").status_code, 404)
        self.assertEqual(Address.objects.get(id=self.address.id).city, "Austin")
        self.assertEqual(OrderInfo.objects.get(id=self.order.id).order_status, "PROCESSING")

    def test_anonymous_is_refused_and_nothing_changes(self):
        anon = _client()
        for res in (
            anon.patch(f"/api/user/update_address/{self.address.id}", {"city": "x"}, format="json"),
            anon.delete(f"/api/user/delete_address/{self.address.id}"),
            anon.get(f"/api/order/{self.order.id}"),
        ):
            self.assertIn(res.status_code, (401, 403, 404))
        self.assertTrue(Address.objects.filter(id=self.address.id, city="Austin").exists())

    def test_guest_order_by_id_needs_the_same_session(self):
        guest_order = OrderInfo.objects.create(
            customer=None, email="g@example.com", order_number="ELW-T-G1",
            order_status="PROCESSING", payment_status="UNPAID",
            sub_total=0, shipping_cost=0, total_amount=0, refound_amount=0, refound_status="", comment="")
        attacker = _client()
        self.assertEqual(attacker.delete(
            f"/api/order/cancel_pending_guest/{guest_order.id}").status_code, 404)
        res = attacker.post("/api/order/confirm_payment_guest",
                            {"order_id": guest_order.id, "paypal_order_id": "X"}, format="json")
        self.assertEqual(res.status_code, 404)
        self.assertEqual(OrderInfo.objects.get(id=guest_order.id).order_status, "PROCESSING")

    def test_owner_gets_200(self):
        owner = self._signed_in(self.owner)
        self.assertEqual(owner.get(f"/api/order/{self.order.id}").status_code, 200)
        self.assertEqual(owner.patch(f"/api/user/update_address/{self.address.id}",
                                     {"city": "Dallas"}, format="json").status_code, 200)
