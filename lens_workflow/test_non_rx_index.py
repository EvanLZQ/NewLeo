"""Non-prescription Classic: plano (0.00) means 1.50 is recommended and
indexes the sheet cannot make at plano are hidden (2026-11-11 QA)."""
from decimal import Decimal
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient

from lens_workflow.models import LensFunctionPath, LensType

SHEET = Path(__file__).resolve().parent / "data" / "price2_fixed.xlsx"


class NonRxClassicIndexTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_shopping_flow_data", verbosity=0)
        call_command("import_lens_prices", str(SHEET), verbosity=0)
        cls.lens_type = LensType.objects.get(code="NON_RX")
        cls.classic = LensFunctionPath.objects.get(
            lens_type=cls.lens_type, function_code="CLEAR", is_active=True)

    def setUp(self):
        self.client = APIClient()
        self.client.defaults["HTTP_X_FORWARDED_PROTO"] = "https"

    def _index_step(self, **extra):
        started = self.client.get("/api/lens-workflow/next/", {
            "current_step_code": "LENS_TYPE", "selected_option_id": self.lens_type.id})
        params = {
            "current_step_code": "FUNCTION",
            "selected_option_id": self.classic.id,
            "selection_path": ",".join(str(i) for i in started.data["selection_path"]),
        }
        params.update(extra)
        res = self.client.get("/api/lens-workflow/next/", params)
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.data["current_step"]["code"], "INDEX")
        return res.data["options"]

    def test_recommends_150_and_hides_unavailable(self):
        options = self._index_step()
        values = [o["metadata"]["index_value"] for o in options]
        recommended = [o for o in options if o["recommended"]]
        self.assertEqual(len(recommended), 1)
        self.assertEqual(Decimal(recommended[0]["metadata"]["index_value"]), Decimal("1.50"))
        self.assertTrue(recommended[0]["metadata"]["is_recommended"])
        self.assertEqual(recommended[0]["group"], "recommended")
        # The real sheet has no plano cell at 1.67 / 1.74 for Classic.
        self.assertNotIn("1.67", values)
        self.assertNotIn("1.74", values)
        self.assertIn("1.50", values)

    def test_stray_prescription_id_is_ignored_for_non_rx(self):
        # A saved Rx left in the client state must not change a plano lens.
        from Prescription.models import PrescriptionInfo
        rx = PrescriptionInfo.objects.create(
            sphere_r=Decimal("-5.00"), sphere_l=Decimal("-5.00"),
            cylinder_r=Decimal("0"), cylinder_l=Decimal("0"))
        options = self._index_step(prescription_id=rx.id)
        recommended = [o for o in options if o["recommended"]]
        self.assertEqual(recommended[0]["metadata"]["index_value"], "1.50")
