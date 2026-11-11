"""Security regression: cart item / prescription upload enumeration.

PR #6 acceptance blocker (2026-11-11): a signed-out visitor could read,
change or delete any cart item not yet on an order by counting up the
sequential ids, and so read a victim's Rx values and uploaded prescription
file (name + public /media link) or detach the upload.

Every by-id cart endpoint must answer 404 to anyone but the owner (signed-in
account or the same guest session); the download view must enforce the same
ownership (staff also allowed); and no response may contain a public
/media/... prescription URL.
"""
import json
import os
import shutil
import tempfile
import uuid

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from Order.models import CompleteSet
from Order.tests import _frame
from Prescription.models import PrescriptionInfo, PrescriptionUpload
from Prescription.testing import rx_via_api

User = get_user_model()

PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


def _client():
    c = APIClient(enforce_csrf_checks=False)
    c.defaults["HTTP_X_FORWARDED_PROTO"] = "https"
    return c


def _body(res):
    if getattr(res, "streaming", False):
        return ""
    return res.content.decode("utf-8", "replace")


class _OwnershipBase(TestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()  # upload throttles
        self._media = tempfile.mkdtemp(prefix="own-media-")
        self._private = tempfile.mkdtemp(prefix="own-private-")
        self._override = override_settings(MEDIA_ROOT=self._media,
                                           PRIVATE_MEDIA_ROOT=self._private)
        self._override.enable()
        self.frame = _frame("OWN-TEST-1", "20.00")
        self.responses = []  # every JSON body we got, checked for /media/

    def tearDown(self):
        self._override.disable()
        shutil.rmtree(self._media, ignore_errors=True)
        shutil.rmtree(self._private, ignore_errors=True)

    def _keep(self, res):
        self.responses.append(_body(res))
        return res

    def _upload(self, client, name="john-doe-rx.pdf"):
        res = self._keep(client.post(
            "/api/prescriptions/upload",
            {"file": SimpleUploadedFile(name, PDF, content_type="application/pdf")},
            format="multipart"))
        self.assertEqual(res.status_code, 201, res.content)
        return res.data["id"]

    def _make_item(self, client, *, signed_in_user=None):
        """Upload a file, type an Rx, create the cart item and put it in the
        cart, exactly as the lens page does."""
        upload_id = self._upload(client)
        rx = rx_via_api(client, sphere_l=-2.25, sphere_r=-2.0, pd_l=31.5, pd_r=31.5)
        self.assertEqual(rx.customer_id, signed_in_user.pk if signed_in_user else None)
        res = self._keep(client.post("/api/order/createcompleteset", {
            "frame": {"sku": self.frame.sku},
            "prescription": {"id": rx.id},
            "prescription_upload": upload_id,
        }, format="json"))
        self.assertEqual(res.status_code, 201, res.content)
        set_id = res.data["id"]
        if signed_in_user is None:
            res = self._keep(client.post("/api/order/guest_cart",
                                         {"action": "add", "complete_set_id": set_id},
                                         format="json"))
        else:
            cart = self._keep(client.post("/api/user/create_shopping_cart", {}, format="json")).data
            res = self._keep(client.patch(f"/api/user/update_shopping_cart/{cart['id']}",
                                          {"eyeglasses_set": [{"id": set_id}]}, format="json"))
        self.assertEqual(res.status_code, 200, res.content)
        self.assertIn(set_id, [s["id"] for s in res.data["eyeglasses_set"]])
        return set_id, upload_id

    def _user(self, name, **extra):
        return User.objects.create_user(username=name, email=f"{name}@example.com",
                                        password="pw-123456", **extra)

    def _signed_in(self, user):
        c = _client()
        c.force_login(user)
        return c

    def _assert_item_untouched(self, set_id, upload_id):
        cs = CompleteSet.objects.get(id=set_id)  # not deleted
        self.assertEqual(str(cs.prescription_upload_id), upload_id)  # not detached

    def _assert_all_404(self, client, set_id, upload_id):
        for method, url, data in (
            ("get", f"/api/order/completeset/{set_id}", None),
            ("get", f"/api/order/completesetloader/{set_id}", None),
            ("patch", f"/api/order/updatecompleteset/{set_id}", {"sub_color": "pwned"}),
            # upload detach / remove
            ("patch", f"/api/order/updatecompleteset/{set_id}", {"prescription_upload": None}),
            ("delete", f"/api/order/deletecompleteset/{set_id}", None),
            ("get", f"/api/prescriptions/upload/{upload_id}/file", None),
        ):
            res = getattr(client, method)(url, data, format="json") if data is not None \
                else getattr(client, method)(url)
            self._keep(res)
            self.assertEqual(res.status_code, 404, f"{method.upper()} {url}: {res.status_code}")
            self.assertNotIn("john-doe-rx", _body(res))
        self._assert_item_untouched(set_id, upload_id)
        self.assertNotEqual(CompleteSet.objects.get(id=set_id).sub_color, "pwned")

    def _assert_cart_claims_refused(self, client, set_id, signed_in):
        """Pulling the victim's id into the attacker's own cart must not work
        (the old claim rule accepted any item not on an order)."""
        if signed_in:
            cart = self._keep(client.post("/api/user/create_shopping_cart", {}, format="json")).data
            res = self._keep(client.patch(f"/api/user/update_shopping_cart/{cart['id']}",
                                          {"eyeglasses_set": [{"id": set_id}]}, format="json"))
        else:
            res = self._keep(client.post("/api/order/guest_cart",
                                         {"action": "add", "complete_set_id": set_id},
                                         format="json"))
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["eyeglasses_set"], [])
        self.assertNotIn("john-doe-rx", _body(res))

    def _assert_no_public_media_urls(self):
        for body in self.responses:
            self.assertNotIn("/media/", body)
            self.assertNotIn("prescription_uploads/", body)


class GuestVictimEnumerationTests(_OwnershipBase):
    def setUp(self):
        super().setUp()
        self.victim = _client()
        self.set_id, self.upload_id = self._make_item(self.victim)

    def test_anonymous_attacker_gets_404_everywhere(self):
        self._assert_all_404(_client(), self.set_id, self.upload_id)
        self._assert_no_public_media_urls()

    def test_anonymous_attacker_cannot_claim_into_own_guest_cart(self):
        attacker = _client()
        self._assert_cart_claims_refused(attacker, self.set_id, signed_in=False)
        self._assert_all_404(attacker, self.set_id, self.upload_id)

    def test_other_signed_in_user_gets_404_everywhere(self):
        other = self._signed_in(self._user("mallory"))
        self._assert_cart_claims_refused(other, self.set_id, signed_in=True)
        self._assert_all_404(other, self.set_id, self.upload_id)
        self._assert_no_public_media_urls()

    def test_owner_guest_session_gets_200(self):
        v = self.victim
        res = self._keep(v.get(f"/api/order/completeset/{self.set_id}"))
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["prescription_upload"]["original_name"], "john-doe-rx.pdf")
        self.assertNotIn("url", res.data["prescription_upload"])
        self.assertEqual(res.data["prescription_upload"]["download_url"],
                         f"/api/prescriptions/upload/{self.upload_id}/file")
        res = self._keep(v.get(f"/api/order/completesetloader/{self.set_id}"))
        self.assertEqual(res.status_code, 200)
        res = self._keep(v.post("/api/order/guest_cart", {"action": "get"}, format="json"))
        self.assertEqual([s["id"] for s in res.data["eyeglasses_set"]], [self.set_id])
        res = self._keep(v.patch(f"/api/order/updatecompleteset/{self.set_id}",
                                 {"prescription_upload": None}, format="json"))
        self.assertEqual(res.status_code, 200)
        self.assertIsNone(CompleteSet.objects.get(id=self.set_id).prescription_upload_id)
        res = self._keep(v.patch(f"/api/order/updatecompleteset/{self.set_id}",
                                 {"prescription_upload": self.upload_id}, format="json"))
        self.assertEqual(res.status_code, 200, res.content)
        res = v.get(f"/api/prescriptions/upload/{self.upload_id}/file")
        self.assertEqual(res.status_code, 200)
        res = v.delete(f"/api/order/deletecompleteset/{self.set_id}")
        self.assertEqual(res.status_code, 204)
        self.assertFalse(CompleteSet.objects.filter(id=self.set_id).exists())
        self._assert_no_public_media_urls()

    def test_guest_items_follow_the_session_into_the_account(self):
        user = self._user("victim-later")
        self.victim.force_login(user)  # same browser session signs in
        res = self._keep(self.victim.get("/api/user/get_user_shopping_cart/0"))
        self.assertEqual([s["id"] for s in res.data["eyeglasses_set"]], [self.set_id])
        self.assertEqual(self.victim.get(f"/api/order/completeset/{self.set_id}").status_code, 200)
        self.assertEqual(
            self.victim.get(f"/api/prescriptions/upload/{self.upload_id}/file").status_code, 200)
        # After sign-out the session (and its guest token) is gone.
        self.victim.logout()
        self._assert_all_404(self.victim, self.set_id, self.upload_id)

    def test_unattached_item_is_not_open_to_everyone(self):
        """The removed fallback: an item in no cart and no order used to be
        readable/editable by anyone."""
        res = self.victim.post("/api/order/createcompleteset",
                               {"frame": {"sku": self.frame.sku}}, format="json")
        loose_id = res.data["id"]
        attacker = _client()
        self.assertEqual(attacker.get(f"/api/order/completeset/{loose_id}").status_code, 404)
        self.assertEqual(attacker.delete(f"/api/order/deletecompleteset/{loose_id}").status_code, 404)
        # Legacy rows (no owner recorded) are not open either.
        legacy = CompleteSet.objects.create(frame=self.frame)
        self.assertEqual(attacker.get(f"/api/order/completeset/{legacy.id}").status_code, 404)
        self.assertEqual(self.victim.get(f"/api/order/completeset/{loose_id}").status_code, 200)

    def test_another_sessions_guest_upload_cannot_be_attached(self):
        attacker = _client()
        res = attacker.post("/api/order/createcompleteset", {
            "frame": {"sku": self.frame.sku}, "prescription_upload": self.upload_id,
        }, format="json")
        self.assertEqual(res.status_code, 400)
        self.assertIn("prescription_upload", res.data)

    def test_missing_ids_look_the_same_as_unowned(self):
        attacker = _client()
        self.assertEqual(attacker.get("/api/order/completeset/999999").status_code, 404)
        self.assertEqual(
            attacker.get(f"/api/prescriptions/upload/{uuid.uuid4()}/file").status_code, 404)


class SignedInVictimEnumerationTests(_OwnershipBase):
    def setUp(self):
        super().setUp()
        self.owner = self._user("john")
        self.victim = self._signed_in(self.owner)
        self.set_id, self.upload_id = self._make_item(self.victim, signed_in_user=self.owner)

    def test_anonymous_attacker_gets_404_everywhere(self):
        self._assert_all_404(_client(), self.set_id, self.upload_id)
        self._assert_no_public_media_urls()

    def test_other_signed_in_user_gets_404_everywhere(self):
        other = self._signed_in(self._user("eve"))
        self._assert_cart_claims_refused(other, self.set_id, signed_in=True)
        self._assert_all_404(other, self.set_id, self.upload_id)
        self._assert_no_public_media_urls()

    def test_other_user_cannot_attach_victims_typed_prescription(self):
        rx_id = CompleteSet.objects.get(id=self.set_id).prescription_id
        other = self._signed_in(self._user("eve2"))
        res = other.post("/api/order/createcompleteset", {
            "frame": {"sku": self.frame.sku}, "prescription": {"id": rx_id},
        }, format="json")
        self.assertEqual(res.status_code, 400)
        self.assertNotIn("-2.25", _body(res))

    def test_owner_gets_200(self):
        v = self.victim
        for url in (f"/api/order/completeset/{self.set_id}",
                    f"/api/order/completesetloader/{self.set_id}",
                    "/api/order/completeset"):
            res = self._keep(v.get(url))
            self.assertEqual(res.status_code, 200, url)
        res = self._keep(v.patch(f"/api/order/updatecompleteset/{self.set_id}",
                                 {"prescription_upload": None}, format="json"))
        self.assertEqual(res.status_code, 200)
        res = self._keep(v.patch(f"/api/order/updatecompleteset/{self.set_id}",
                                 {"prescription_upload": {"id": self.upload_id}}, format="json"))
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(v.delete(f"/api/order/deletecompleteset/{self.set_id}").status_code, 204)
        self._assert_no_public_media_urls()


class PrescriptionDownloadViewTests(_OwnershipBase):
    def setUp(self):
        super().setUp()
        self.owner = self._user("rx-owner")
        self.victim = self._signed_in(self.owner)
        self.set_id, self.upload_id = self._make_item(self.victim, signed_in_user=self.owner)
        self.url = f"/api/prescriptions/upload/{self.upload_id}/file"

    def test_owner_gets_file_with_safe_headers(self):
        res = self.victim.get(self.url)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(b"".join(res.streaming_content), PDF)
        self.assertEqual(res["Content-Type"], "application/pdf")
        self.assertEqual(res["X-Content-Type-Options"], "nosniff")
        self.assertTrue(res["Content-Disposition"].startswith("attachment"))
        self.assertIn("john-doe-rx.pdf", res["Content-Disposition"])
        self.assertIn("no-store", res["Cache-Control"])

    def test_anonymous_and_other_user_get_404(self):
        self.assertEqual(_client().get(self.url).status_code, 404)
        self.assertEqual(self._signed_in(self._user("snoop")).get(self.url).status_code, 404)

    def test_staff_is_allowed(self):
        staff = self._signed_in(self._user("optician", is_staff=True))
        res = staff.get(self.url)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res["X-Content-Type-Options"], "nosniff")

    def test_file_is_stored_outside_public_media(self):
        upload = PrescriptionUpload.objects.get(pk=self.upload_id)
        self.assertTrue(os.path.isfile(os.path.join(self._private, upload.file.name)))
        self.assertFalse(os.path.exists(os.path.join(self._media, upload.file.name)))
        self.assertEqual(os.listdir(self._media), [])
        with self.assertRaises(ValueError):
            upload.file.url  # private storage has no URL
        mode = os.stat(os.path.join(self._private, upload.file.name)).st_mode & 0o777
        self.assertEqual(mode, 0o600)

    def test_upload_response_has_no_public_url(self):
        body = json.loads(self.responses[0])
        self.assertNotIn("url", body)
        self.assertTrue(body["download_url"].startswith("/api/prescriptions/upload/"))
        self._assert_no_public_media_urls()


class MovePublicUploadsTests(TestCase):
    """Uploads already saved under MEDIA_ROOT/prescription_uploads by the
    first PR #6 build are moved to private storage (migration 0012 and the
    move_prescription_uploads_private command)."""

    def test_moves_files_and_removes_public_copies(self):
        from django.core.management import call_command
        media = tempfile.mkdtemp(prefix="mv-media-")
        private = tempfile.mkdtemp(prefix="mv-private-")
        try:
            rel = "prescription_uploads/2026/11/abc123.pdf"
            os.makedirs(os.path.join(media, os.path.dirname(rel)))
            with open(os.path.join(media, rel), "wb") as fh:
                fh.write(PDF)
            os.makedirs(os.path.join(media, "product_images"))
            with override_settings(MEDIA_ROOT=media, PRIVATE_MEDIA_ROOT=private):
                call_command("move_prescription_uploads_private", stdout=open(os.devnull, "w"))
                call_command("move_prescription_uploads_private", stdout=open(os.devnull, "w"))
            self.assertFalse(os.path.exists(os.path.join(media, "prescription_uploads")))
            self.assertTrue(os.path.isdir(os.path.join(media, "product_images")))
            with open(os.path.join(private, rel), "rb") as fh:
                self.assertEqual(fh.read(), PDF)
        finally:
            shutil.rmtree(media, ignore_errors=True)
            shutil.rmtree(private, ignore_errors=True)
