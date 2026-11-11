"""Prescription photo / PDF upload (2026-11-11 QA, issue 1)."""
import io
import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from PIL import Image
from rest_framework.test import APIClient

from Order.models import CompleteSet
from Order.tests import _frame
from Prescription.models import PrescriptionUpload

User = get_user_model()
URL = "/api/prescriptions/upload"


def _png_bytes():
    buf = io.BytesIO()
    Image.new("RGB", (20, 10), (200, 200, 200)).save(buf, format="PNG")
    return buf.getvalue()


def _jpeg_bytes():
    buf = io.BytesIO()
    Image.new("RGB", (20, 10), (10, 20, 30)).save(buf, format="JPEG")
    return buf.getvalue()


PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


class _MediaTmp(TestCase):
    def setUp(self):
        self._media = tempfile.mkdtemp(prefix="rx-upload-test-")
        self._override = override_settings(MEDIA_ROOT=self._media)
        self._override.enable()
        self.client = APIClient(enforce_csrf_checks=False)
        self.client.defaults["HTTP_X_FORWARDED_PROTO"] = "https"
        from django.core.cache import cache
        cache.clear()  # throttles

    def tearDown(self):
        self._override.disable()
        shutil.rmtree(self._media, ignore_errors=True)

    def _post(self, name, data, content_type="application/octet-stream"):
        return self.client.post(
            URL, {"file": SimpleUploadedFile(name, data, content_type=content_type)},
            format="multipart")


class UploadValidationTests(_MediaTmp):
    def test_png_jpeg_pdf_are_accepted(self):
        for name, data, kind in (
            ("rx.png", _png_bytes(), "image/png"),
            ("rx.JPG", _jpeg_bytes(), "image/jpeg"),
            ("rx.pdf", PDF, "application/pdf"),
        ):
            res = self._post(name, data)
            self.assertEqual(res.status_code, 201, res.content)
            self.assertEqual(res.data["content_type"], kind)
            self.assertEqual(res.data["original_name"], name)
            upload = PrescriptionUpload.objects.get(id=res.data["id"])
            self.assertTrue(upload.file.name.startswith("prescription_uploads/"))
            # Stored under a random name, not the shopper's file name.
            self.assertNotIn("rx", upload.file.name.rsplit("/", 1)[-1].lower())
            self.assertIsNone(upload.customer)

    def test_type_comes_from_the_bytes_not_the_name(self):
        res = self._post("rx.png", b"MZ\x90\x00 not an image at all")
        self.assertEqual(res.status_code, 400)
        res = self._post("rx.pdf", _png_bytes())  # PNG bytes named .pdf
        self.assertEqual(res.status_code, 400)
        res = self._post("rx.html", b"<html><script>alert(1)</script>")
        self.assertEqual(res.status_code, 400)
        self.assertEqual(PrescriptionUpload.objects.count(), 0)

    def test_broken_image_and_pdf_are_rejected(self):
        self.assertEqual(self._post("rx.png", b"\x89PNG\r\n\x1a\n" + b"0" * 50).status_code, 400)
        self.assertEqual(self._post("rx.pdf", b"%PDF-1.4\nno end marker").status_code, 400)

    @override_settings(PRESCRIPTION_UPLOAD_MAX_BYTES=1024)
    def test_size_limit(self):
        res = self._post("rx.pdf", b"%PDF-1.4\n" + b"0" * 2048 + b"\n%%EOF")
        self.assertEqual(res.status_code, 400)
        self.assertIn("too large", res.data["error"])

    def test_default_limit_is_10mb(self):
        from Prescription.uploads import DEFAULT_MAX_BYTES, max_bytes
        self.assertEqual(DEFAULT_MAX_BYTES, 10 * 1024 * 1024)
        self.assertEqual(max_bytes(), DEFAULT_MAX_BYTES)

    def test_missing_file(self):
        res = self.client.post(URL, {}, format="multipart")
        self.assertEqual(res.status_code, 400)


class UploadLinkTests(_MediaTmp):
    def setUp(self):
        super().setUp()
        self.frame = _frame("RX-UPLOAD-1", "20.00")

    def test_guest_upload_links_to_cart_item_and_reads_back(self):
        upload_id = self._post("rx.pdf", PDF).data["id"]
        res = self.client.post("/api/order/createcompleteset", {
            "frame": {"sku": self.frame.sku},
            "prescription_upload": upload_id,
        }, format="json")
        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual(res.data["prescription_upload"]["id"], upload_id)
        self.assertTrue(res.data["prescription_upload"]["is_pdf"])
        cs = CompleteSet.objects.get(id=res.data["id"])
        self.assertEqual(str(cs.prescription_upload_id), upload_id)

        # Detach with an explicit null.
        res = self.client.patch(f"/api/order/updatecompleteset/{cs.id}",
                                {"prescription_upload": None}, format="json")
        self.assertEqual(res.status_code, 200, res.content)
        cs.refresh_from_db()
        self.assertIsNone(cs.prescription_upload_id)
        # And attach again through PATCH, using the read shape.
        res = self.client.patch(f"/api/order/updatecompleteset/{cs.id}",
                                {"prescription_upload": {"id": upload_id}}, format="json")
        self.assertEqual(res.status_code, 200, res.content)
        cs.refresh_from_db()
        self.assertEqual(str(cs.prescription_upload_id), upload_id)

    def test_another_accounts_upload_cannot_be_attached(self):
        owner = User.objects.create_user(username="owner", email="o@example.com", password="x")
        upload = PrescriptionUpload.objects.create(
            customer=owner, original_name="a.pdf", content_type="application/pdf",
            size=10, file="prescription_uploads/x.pdf")
        res = self.client.post("/api/order/createcompleteset", {
            "frame": {"sku": self.frame.sku},
            "prescription_upload": str(upload.id),
        }, format="json")
        self.assertEqual(res.status_code, 400)
        self.assertIn("prescription_upload", res.data)

    def test_signed_in_upload_is_owned(self):
        user = User.objects.create_user(username="u1", email="u1@example.com", password="x")
        self.client.force_authenticate(user)
        res = self._post("rx.png", _png_bytes())
        self.assertEqual(res.status_code, 201)
        upload = PrescriptionUpload.objects.get(id=res.data["id"])
        self.assertEqual(upload.customer_id, user.pk)


class UploadAdminTests(_MediaTmp):
    def test_admin_pages_render(self):
        admin = User.objects.create_superuser(username="adm", email="a@example.com", password="x")
        self.client.force_login(admin)
        upload_id = self._post("rx.png", _png_bytes()).data["id"]
        frame = _frame("RX-UPLOAD-2", "20.00")
        cs = CompleteSet.objects.create(frame=frame, prescription_upload_id=upload_id)
        for url in (
            "/admin/Prescription/prescriptionupload/",
            f"/admin/Prescription/prescriptionupload/{upload_id}/change/",
            "/admin/Order/completeset/",
            f"/admin/Order/completeset/{cs.id}/change/",
        ):
            res = self.client.get(url, secure=True)
            self.assertEqual(res.status_code, 200, url)
        res = self.client.get("/admin/Prescription/prescriptionupload/", secure=True)
        self.assertContains(res, f"#{cs.id}")
