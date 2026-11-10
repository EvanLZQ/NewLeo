"""Rx quote, price-sheet rules, and the real price2_fixed.xlsx import."""
from decimal import Decimal
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient

from lens_workflow import price_table as pt
from lens_workflow.models import (
    LensFunctionPath,
    LensIndexOption,
    LensPriceBlock,
    LensPriceCell,
    LensType,
)
from lens_workflow.pricing import (
    MAX_CYL_MESSAGE,
    REASON_COLOR,
    REASON_GRADIENT,
    REASON_NOT_OFFERED,
    Eye,
    QuoteRequest,
    quote,
)
from lens_workflow.tests import block, workbook

PRICE_FILE = Path(__file__).resolve().parent / "data" / "price2_fixed.xlsx"
D = Decimal


def _eye(sph=0, cyl=0):
    return Eye(sph=D(str(sph)), cyl=D(str(cyl)))


def _request(**overrides):
    data = dict(
        od=_eye(), os=_eye(), lens_type_code="SVD", function_code="CLEAR",
        index_value=D("1.50"))
    data.update(overrides)
    return QuoteRequest(**data)


class RuleTests(TestCase):
    """Premium, then Economic; free upgrade; max cylinder; unresolved color."""

    def setUp(self):
        prem_150 = [[9.95, "N", 9.95], [9.95, "N", 9.95], ["N", "N", "N"]]
        prem_156 = [[19.95, 19.95, "N"], [19.95, 19.95, "N"], ["N", "N", "N"]]
        eco_150 = [[4.95, 4.95, 4.95], [4.95, 4.95, 4.95], [4.95, 4.95, 4.95]]
        sheets = {
            "Premium Lens": (
                block(index=1.5, prices=prem_150, note="Free Upgrade to 1.56")
                + block(index=1.56, prices=prem_156)
                + block(index=1.6, prices=[[14.95, 14.95, "N"]] * 3)
                + block(index=1.5, lens="Sun/Tint", color="Color Table", depth="30%, 50%",
                        prices=[[99.95, 99.95, 99.95]] * 3)
            ),
            "Economic Lens": (
                block(index=1.5, prices=eco_150)
                + block(index=1.56, lens="Clear", color=None, prices=[[44.95, 44.95, 44.95]] * 3)
            ),
        }
        pt.apply_import(pt.parse_workbook(workbook(sheets)), filename="rules.xlsx", file_bytes=b"x")

    def test_premium_wins_when_it_has_a_cell(self):
        result = quote(_request(), include_options=False)
        self.assertTrue(result.available)
        self.assertEqual(result.selection.lens_price, D("9.95"))
        self.assertEqual(result.selection.tier, "premium")
        self.assertFalse(result.selection.free_upgrade)
        self.assertEqual(result.selection.lens_index, D("1.50"))

    def test_free_upgrade_uses_the_156_cell(self):
        result = quote(_request(od=_eye(cyl=-0.25), os=_eye(cyl=-0.25)), include_options=False)
        self.assertEqual(
            (result.selection.tier, result.selection.lens_price,
             result.selection.lens_index, result.selection.free_upgrade),
            ("premium", D("19.95"), D("1.56"), True))

    def test_economic_fallback_when_premium_is_n(self):
        # Sphere -0.50 is N on Premium 1.50 and on the 1.56 upgrade.
        result = quote(_request(od=_eye(sph=-0.5), os=_eye(sph=-0.5)), include_options=False)
        self.assertEqual(result.selection.tier, "economic")
        self.assertEqual(result.selection.lens_price, D("4.95"))
        self.assertFalse(result.selection.free_upgrade)

    def test_catalog_161_uses_the_sheet_160_cell(self):
        self.assertIsNone(pt.lookup_price(
            "Single Vision Distance", "Clear", "N", "N", "N",
            D("1.61"), D("0"), D("0")))
        result = quote(_request(index_value=D("1.61")), include_options=False)
        self.assertEqual(result.selection.lens_price, D("14.95"))
        self.assertEqual(result.selection.lens_index, D("1.60"))
        self.assertEqual(result.selection.catalog_index, D("1.61"))
        self.assertEqual(result.selection.tier, "premium")

    def test_empty_color_is_not_sold_as_clear(self):
        self.assertEqual(
            LensPriceBlock.objects.get(tier="economic", lens_index=D("1.56")).color, "")
        self.assertIsNone(pt.lookup_price(
            "Single Vision Distance", "Clear", "", "N", "N",
            D("1.56"), D("0"), D("0")))
        # Premium has no 1.56 cell at cylinder -0.50, and the economic row's
        # blank color must not fill that hole with 44.95.
        result = quote(
            _request(index_value=D("1.56"), od=_eye(cyl=-0.5), os=_eye(cyl=-0.5)),
            include_options=False)
        self.assertFalse(result.available)
        self.assertEqual(result.selection.reason, REASON_NOT_OFFERED)

    def test_color_table_prices_are_stored_and_not_offered(self):
        block_row = LensPriceBlock.objects.get(tier="premium", color="Color Table")
        self.assertGreater(block_row.cells.count(), 0)
        self.assertIsNone(pt.lookup_price(
            "Single Vision Distance", "Sun/Tint", "Color Table", "30%, 50%", "N",
            D("1.50"), D("0"), D("0")))
        result = quote(_request(
            function_code="SUN", sun_type="MIRRORED", color_name="Mirrored Blue",
            index_value=D("1.50")), include_options=False)
        self.assertFalse(result.available)
        self.assertEqual(result.selection.reason, REASON_COLOR)

    def test_gradient_is_not_priced_from_another_table(self):
        result = quote(_request(
            function_code="SUN", sun_type="GRADIENT", color_name="Gradient Gray",
            index_value=D("1.50")), include_options=False)
        self.assertEqual(result.selection.reason, REASON_GRADIENT)

    def test_max_cylinder_blocks_with_the_exact_message(self):
        result = quote(_request(od=_eye(cyl=-6.25), os=_eye()), include_options=False)
        self.assertTrue(result.blocked)
        self.assertEqual(result.block_reason, MAX_CYL_MESSAGE)
        self.assertIsNone(result.total_lens_price)
        # 6.00 exactly is the last column the sheet allows, not a block.
        allowed = quote(_request(od=_eye(cyl=-6), os=_eye(cyl=-6)), include_options=False)
        self.assertFalse(allowed.blocked)

    def test_pair_price_is_the_higher_eye_not_the_sum(self):
        # OD is the premium plano cell ($9.95). OS sphere -0.50 is N on Premium
        # 1.50 and on the 1.56 upgrade, so that eye is the economic $4.95 cell.
        result = quote(_request(od=_eye(), os=_eye(sph=-0.5)), include_options=False)
        self.assertEqual(result.selection.lens_price, D("9.95"))
        self.assertEqual(result.priced_eye, "od")
        self.assertEqual(result.total_lens_price, D("9.95"))

    def test_one_eye_off_the_grid_hides_the_pair(self):
        result = quote(_request(od=_eye(sph=-9), os=_eye()), include_options=False)
        self.assertFalse(result.available)
        self.assertEqual(result.selection.reason, REASON_NOT_OFFERED)

    def test_empty_table_uses_catalog_prices_and_logs(self):
        LensPriceBlock.objects.all().delete()
        lens_type = LensType.objects.create(
            code="SVD", label="Single Vision Distance", is_prescription_required=True)
        function = LensFunctionPath.objects.create(
            lens_type=lens_type, function_code="CLEAR", function_label="Classic",
            extra_price=D("0"))
        index = LensIndexOption.objects.create(
            lens_type=lens_type, tier="Basic", option_label="Basic - 1.50 Index",
            index_value=D("1.50"), price=D("4.95"))
        with self.assertLogs("lens_workflow.pricing", level="WARNING") as logs:
            result = quote(_request(
                lens_type=lens_type, function_path=function, index_option=index,
                index_value=D("1.50")), include_options=False)
        self.assertEqual(result.pricing_source, "legacy")
        self.assertEqual(result.total_lens_price, D("4.95"))
        self.assertTrue(any("price table is empty" in line for line in logs.output))


class RxQuoteApiTests(TestCase):
    def setUp(self):
        pt.apply_import(pt.parse_workbook(workbook({
            "Premium Lens": block(index=1.5, prices=[[9.95, 9.95, 9.95]] * 3),
            "Economic Lens": block(index=1.5, prices=[[4.95, 4.95, 4.95]] * 3),
        })), filename="api.xlsx", file_bytes=b"x")
        self.client = APIClient()
        self.client.defaults["HTTP_X_FORWARDED_PROTO"] = "https"

    def _post(self, **extra):
        body = {
            "od": {"sph": "0", "cyl": "0", "add": "0", "pd": "32"},
            "os": {"sph": "0", "cyl": "0", "add": "0", "pd": "31.5"},
            "lens_type_code": "SVD",
            "function_code": "CLEAR",
            "index_value": "1.50",
            "price": "1.00",
        }
        body.update(extra)
        return self.client.post("/api/lens-workflow/rx-quote/", body, format="json")

    def test_quote_uses_the_sheet_and_ignores_a_client_price(self):
        response = self._post()
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["pricing_source"], "price_table")
        self.assertEqual(response.data["selection"]["lens_price"], "9.95")
        self.assertEqual(response.data["selection"]["tier"], "premium")
        self.assertEqual(response.data["selection"]["lens_type"], "Clear")
        self.assertEqual(response.data["selection"]["color"], "N")
        self.assertEqual(response.data["selection"]["coating"], "N")
        self.assertEqual(response.data["total_lens_price"], "9.95")
        self.assertFalse(response.data["blocked"])
        self.assertTrue(response.data["options"])

    def test_max_cylinder_is_the_exact_string(self):
        response = self._post(od={"sph": "0", "cyl": "-6.50"})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["block_reason"], "Max CYL is 6.00D")
        self.assertTrue(response.data["blocked"])
        self.assertIsNone(response.data["total_lens_price"])
        self.assertEqual(response.data["options"], [])

    def test_missing_lens_type_is_a_client_error(self):
        response = self.client.post("/api/lens-workflow/rx-quote/", {
            "od": {"sph": "0"}, "os": {"sph": "0"},
        }, format="json")
        self.assertEqual(response.status_code, 400)

    def test_prism_is_added_because_the_sheet_has_no_prism_column(self):
        response = self._post(prism=True)
        self.assertEqual(response.data["prism"], {"applied": True, "price": "27.00"})
        self.assertEqual(response.data["total_lens_price"], "36.95")
        self.assertEqual(response.data["selection"]["lens_price"], "9.95")

    def test_summary_matches_the_quote(self):
        lens_type = LensType.objects.create(
            code="SVD", label="Single Vision Distance", is_prescription_required=True)
        function = LensFunctionPath.objects.create(
            lens_type=lens_type, function_code="CLEAR", function_label="Classic",
            extra_price=D("0"))
        index = LensIndexOption.objects.create(
            lens_type=lens_type, tier="Basic", option_label="Basic - 1.50 Index",
            index_value=D("1.50"), price=D("4.95"))
        response = self.client.get("/api/lens-workflow/summary/", {
            "lens_type_id": lens_type.id,
            "function_path_id": function.id,
            "index_option_id": index.id,
            "od_sph": "0", "od_cyl": "0", "os_sph": "0", "os_cyl": "0",
        })
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["pricing_source"], "price_table")
        self.assertEqual(response.data["total_add_on_price"], "9.95")
        self.assertEqual(response.data["quote"]["selection"]["lens_price"], "9.95")


class RealPriceSheetTests(TestCase):
    """The attached price2_fixed.xlsx, imported the way production will."""

    @classmethod
    def setUpTestData(cls):
        call_command("import_lens_prices", str(PRICE_FILE))

    def test_file_parses_and_skips_conant_row_and_blank_color(self):
        with PRICE_FILE.open("rb") as handle:
            parsed = pt.parse_workbook(handle)
        self.assertTrue(parsed.ok, [e.message for e in parsed.errors])
        conant = [w for w in parsed.warnings if "Conant" in w.message]
        self.assertTrue(conant, "row 281 Conant/MAAT should be ignored, not imported as a price")
        self.assertIn("281", conant[0].message)
        blanks = [w for w in parsed.warnings if "Color is empty" in w.message]
        self.assertEqual(len(blanks), 4)
        self.assertEqual(LensPriceCell.objects.filter(block__tier="premium").count(), 24321)
        self.assertEqual(LensPriceCell.objects.filter(block__tier="economic").count(), 35707)
        photo = LensPriceBlock.objects.get(
            tier="premium", prescription_type="Single Vision Distance",
            lens_type="Photochromic", color="Gray, Brown", coating="N",
            lens_index=D("1.60"))
        self.assertGreater(photo.cells.count(), 0)

    def test_import_is_idempotent(self):
        before = LensPriceCell.objects.count()
        call_command("import_lens_prices", str(PRICE_FILE), "--dry-run")
        self.assertEqual(LensPriceCell.objects.count(), before)
        call_command("import_lens_prices", str(PRICE_FILE))
        self.assertEqual(LensPriceCell.objects.count(), before)
        self.assertEqual(LensPriceBlock.objects.count(), 95 + 125)

    def test_sheet_gaps_are_not_sellable(self):
        empty = LensPriceBlock.objects.filter(color="")
        self.assertEqual(
            set(empty.values_list("tier", "prescription_type", "lens_type", "lens_index")),
            {
                ("economic", "Progressive", "Clear", D("1.56")),
                ("economic", "Progressive", "Clear", D("1.60")),
                ("economic", "Progressive", "Clear", D("1.67")),
                ("economic", "Progressive", "Clear", D("1.74")),
            })
        self.assertGreater(
            LensPriceBlock.objects.filter(color__iexact="Color Table").count(), 0)
        # Drop the real Premium 1.56 progressive row. The economic row still
        # has prices, but its color cell is blank, so the power stays unavailable.
        LensPriceBlock.objects.filter(
            tier="premium", prescription_type="Progressive", lens_type="Clear",
            lens_index=D("1.56")).delete()
        self.assertTrue(LensPriceCell.objects.filter(
            block__tier="economic", block__color="", block__lens_index=D("1.56"),
            sphere=D("0"), cylinder=D("0")).exists())
        self.assertIsNone(pt.lookup_price(
            "Progressive", "Clear", "N", "N", "N", D("1.56"), D("0"), D("0")))

    def _both(self, sph=0, cyl=0, **extra):
        return quote(_request(
            od=_eye(sph, cyl), os=_eye(sph, cyl), **extra), include_options=False)

    def test_worked_examples(self):
        clear_150 = self._both()
        self.assertEqual(
            (clear_150.selection.tier, clear_150.selection.lens_price, clear_150.selection.lens_index),
            ("premium", D("9.95"), D("1.50")))

        clear_161 = self._both(index_value=D("1.61"))
        self.assertEqual(clear_161.selection.lens_price, D("14.95"))
        self.assertEqual(clear_161.selection.lens_index, D("1.60"))
        self.assertEqual(clear_161.selection.tier, "premium")

        progressive = self._both(lens_type_code="PROGRESSIVE", index_value=D("1.50"))
        self.assertEqual(progressive.selection.lens_price, D("109.95"))
        self.assertEqual(progressive.selection.tier, "premium")
        self.assertFalse(progressive.selection.free_upgrade)

        photo = self._both(
            function_code="PHOTOCHROMIC", color_name="Grey", index_value=D("1.56"))
        self.assertEqual(photo.selection.lens_price, D("19.95"))
        self.assertEqual(photo.selection.tier, "premium")
        self.assertEqual(photo.selection.color, "Gray, Brown")

        thin = self._both(index_value=D("1.74"), sph=-6)
        self.assertEqual(thin.selection.lens_price, D("99.95"))
        self.assertEqual(thin.selection.tier, "premium")
        self.assertEqual(thin.selection.lens_index, D("1.74"))

        # Premium 1.60 stops at cylinder -2.00. Economic has -2.25.
        fallback = self._both(index_value=D("1.60"), cyl=-2.25)
        self.assertEqual(fallback.selection.tier, "economic")
        self.assertEqual(fallback.selection.lens_price, D("19.95"))

        upgrade = self._both(lens_type_code="PROGRESSIVE", index_value=D("1.50"), sph=-2)
        self.assertTrue(upgrade.selection.free_upgrade)
        self.assertEqual(upgrade.selection.lens_index, D("1.56"))
        self.assertEqual(upgrade.selection.lens_price, D("109.95"))
        self.assertEqual(upgrade.selection.tier, "premium")

        # Farsighted single-vision photochromic is not on this sheet.
        far = self._both(function_code="PHOTOCHROMIC", color_name="Gray",
                         index_value=D("1.56"), sph=2)
        self.assertFalse(far.available)

        solid = self._both(
            function_code="SUN", sun_type="SOLID", color_name="50% Gray",
            index_value=D("1.50"))
        self.assertEqual(solid.selection.tier, "economic")
        self.assertEqual(solid.selection.lens_price, D("39.95"))
        dark = self._both(
            function_code="SUN", sun_type="SOLID", color_name="80% Gray",
            index_value=D("1.50"))
        self.assertEqual(dark.selection.lens_price, D("9.95"))
        self.assertEqual(dark.selection.depth, "0.8")

    def test_api_against_the_real_file(self):
        client = APIClient()
        client.defaults["HTTP_X_FORWARDED_PROTO"] = "https"
        response = client.post("/api/lens-workflow/rx-quote/", {
            "od": {"sph": "-6.00", "cyl": "0", "add": "0", "pd": "30"},
            "os": {"sph": "-6.00", "cyl": "0", "add": "0", "pd": "30"},
            "lens_type_code": "SVD",
            "function_code": "CLEAR",
            "index_value": "1.74",
            "price": "0.01",
        }, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["selection"]["lens_price"], "99.95")
        self.assertEqual(response.data["total_lens_price"], "99.95")
        self.assertEqual(response.data["pricing_source"], "price_table")
