"""Steep-meridian index recommendation, neighbor tiers, and blue-light exclusivity."""
import importlib
from decimal import Decimal
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.color import no_style
from django.db import connection
from django.test import TestCase
from rest_framework.test import APIClient

from General.models import Address
from Order.models import CompleteSet
from Order.tests import _address_fields, _frame
from Prescription.models import PrescriptionInfo
from lens_workflow import price_table as pt
from lens_workflow.management.commands.seed_shopping_flow_data import (
    INDEX_RATIONALE,
    INDEX_TIERS_FULL,
    INDEX_TIERS_NARROW,
    INDEX_TIERS_SVD,
)
deactivate_retired_index_options = importlib.import_module(
    "lens_workflow.migrations.0014_retire_offsheet_indexes"
).deactivate_retired_index_options
from lens_workflow.models import (
    LensCoating,
    LensColorOption,
    LensFunctionPath,
    LensIndexOption,
    LensIndexRecommendationRule,
    LensPriceCell,
    LensReaderStrength,
    LensType,
)
from lens_workflow.tests import HEADER, block, workbook
from lens_workflow.views import _combined_power

D = Decimal
User = get_user_model()


def _selection_query(path):
    """Query-string form of a selection_path the API just returned."""
    parts = []
    for item in path or []:
        if isinstance(item, dict):
            step = item.get("step") or ""
            parts.append(f"{step}:{item['id']}" if step else str(item["id"]))
        else:
            parts.append(str(item))
    return ",".join(parts)

SPHERES = [
    0, -0.25, 0.25, -0.5, 0.5, -1, 1, -2, 2, -2.25, 2.25,
    -3, 3, -4, 4, -4.25, 4.25, -5, 5, -6, 6, -6.25, 6.25, -8, 8,
]
CYLS = [0, -0.25, -1, -1.25, -2, -2.5, -3.5, -4, -6]
SHEET_PRICE = {
    D("1.50"): 9.95,
    D("1.56"): 12.95,
    D("1.60"): 14.95,
    D("1.67"): 39.95,
    D("1.74"): 99.95,
}
CATALOG = [
    ("1.50", "4.95", "Basic", "Basic - 1.50 Index"),
    ("1.56", "6.95", "Standard", "Standard - 1.56 Index"),
    ("1.61", "19.95", "Popular", "Popular - 1.61 Index"),
    ("1.67", "39.95", "Advanced", "Advanced - 1.67 Index"),
    ("1.74", "79.95", "Premium", "Premium - 1.74 Index"),
]


def _grid(index, material, price):
    rows = [HEADER + CYLS]
    for n, sph in enumerate(SPHERES):
        if n == 0:
            meta = ["", "", "", None, "Single Vision Distance", "Clear",
                    "N", "N", "N", index, material]
        else:
            meta = [None] * 11
        rows.append(meta + [sph] + [price] * len(CYLS))
    return rows


def _import_full_sheet():
    sheets = {"Premium Lens": [["Premium Lens (Conant)"], []]}
    for index, price in SHEET_PRICE.items():
        sheets["Premium Lens"] += _grid(float(index), "material", price)
    parsed = pt.parse_workbook(workbook(sheets))
    if not parsed.ok:
        raise AssertionError([e.message for e in parsed.errors])
    pt.apply_import(parsed, filename="recommendation.xlsx", file_bytes=b"x")


class SteepMeridianTests(TestCase):
    """The power is max(|S|, |S+C|) on the stronger eye, not spherical equivalent."""

    def test_mixed_sign_cylinder_uses_the_steeper_meridian(self):
        # S -1.00 / C -2.00 → meridians 1.00 and 3.00. SE would be 2.00.
        rx = PrescriptionInfo.objects.create(
            sphere_r=D("-1.00"), cylinder_r=D("-2.00"),
            sphere_l=D("-1.00"), cylinder_l=D("-2.00"))
        power, _direction = _combined_power(rx)
        self.assertEqual(power, D("3.00"))

        # S +1.00 / C -4.50 → meridians 1.00 and 3.50. SE would be 1.25.
        mixed = PrescriptionInfo.objects.create(
            sphere_r=D("1.00"), cylinder_r=D("-4.50"),
            sphere_l=D("0"), cylinder_l=D("0"))
        power, _direction = _combined_power(mixed)
        self.assertEqual(power, D("3.50"))

    def test_the_higher_power_eye_decides(self):
        # OD is barely off plano. OS meridians are 5.00 and 6.25.
        rx = PrescriptionInfo.objects.create(
            sphere_r=D("-0.25"), cylinder_r=D("0"),
            sphere_l=D("-5.00"), cylinder_l=D("-1.25"))
        power, _direction = _combined_power(rx)
        self.assertEqual(power, D("6.25"))

        swapped = PrescriptionInfo.objects.create(
            sphere_r=D("-5.00"), cylinder_r=D("-1.25"),
            sphere_l=D("-0.25"), cylinder_l=D("0"))
        power, _direction = _combined_power(swapped)
        self.assertEqual(power, D("6.25"))


class IndexMenuTests(TestCase):
    """`/next/` index step: one badge, neighbor tiers, sheet holes, one price."""

    @classmethod
    def setUpTestData(cls):
        _import_full_sheet()
        cls.lens_type = LensType.objects.create(
            code="SVD", label="Single Vision Distance",
            is_prescription_required=True,
            index_recommendation_category="SINGLE_VISION",
            is_active=True, sort_order=10)
        cls.classic = LensFunctionPath.objects.create(
            lens_type=cls.lens_type, function_code="CLEAR", function_label="Classic",
            color_required=False, extra_price=D("0"), is_active=True)
        for sort_idx, (index_value, price, tier, label) in enumerate(CATALOG, start=1):
            LensIndexOption.objects.create(
                lens_type=cls.lens_type, index_value=D(index_value), tier=tier,
                option_label=label, price=D(price), sort_order=sort_idx * 10,
                is_active=True)

    def setUp(self):
        self.client = APIClient()
        self.client.defaults["HTTP_X_FORWARDED_PROTO"] = "https"

    def _menu(self, *, sph_r, cyl_r=0, sph_l=None, cyl_l=None):
        if sph_l is None:
            sph_l = sph_r
        if cyl_l is None:
            cyl_l = cyl_r
        rx = PrescriptionInfo.objects.create(
            sphere_r=D(str(sph_r)), cylinder_r=D(str(cyl_r)),
            sphere_l=D(str(sph_l)), cylinder_l=D(str(cyl_l)))
        started = self.client.get("/api/lens-workflow/next/", {
            "current_step_code": "LENS_TYPE",
            "selected_option_id": self.lens_type.id,
        })
        self.assertEqual(started.status_code, 200, started.content)
        menu = self.client.get("/api/lens-workflow/next/", {
            "current_step_code": "FUNCTION",
            "selected_option_id": self.classic.id,
            "selection_path": _selection_query(started.data["selection_path"]),
            "prescription_id": rx.id,
        })
        self.assertEqual(menu.status_code, 200, menu.content)
        self.assertEqual(menu.data["current_step"]["code"], "INDEX")
        return menu.data["options"], rx

    def _by_index(self, options):
        return {opt["metadata"]["index_value"]: opt for opt in options}

    def _recommended(self, options):
        badges = [opt for opt in options if opt["recommended"]]
        self.assertEqual(len(badges), 1, options)
        self.assertEqual(
            [opt for opt in options if opt["metadata"]["is_recommended"]],
            badges)
        self.assertEqual(badges[0]["group"], "recommended")
        return badges[0]

    def test_bracket_boundaries_both_signs(self):
        cases = [
            ("0", "1.50"),
            ("2.00", "1.50"),
            ("-2.00", "1.50"),
            ("2.25", "1.61"),
            ("-2.25", "1.61"),
            ("4.00", "1.61"),
            ("-4.00", "1.61"),
            ("4.25", "1.67"),
            ("-4.25", "1.67"),
            ("6.00", "1.67"),
            ("-6.00", "1.67"),
            ("6.25", "1.74"),
            ("-6.25", "1.74"),
            ("8.00", "1.74"),
        ]
        profiles = {
            "1.50": ("CR-39", "58.0"),
            "1.61": ("MR-8", "41.0"),
            "1.67": ("MR-7 / MR-10", "31.0"),
            "1.74": ("MR-174", "32.0"),
        }
        for power, index_value in cases:
            options, _rx = self._menu(sph_r=power)
            winner = self._recommended(options)
            self.assertEqual(
                winner["metadata"]["index_value"], index_value,
                f"{power} recommended {winner['metadata']['index_value']}")
            material, abbe = profiles[index_value]
            self.assertEqual(winner["material"], material)
            self.assertEqual(winner["abbe_number"], abbe)
            self.assertEqual(winner["metadata"]["material"], material)
            self.assertEqual(winner["metadata"]["abbe_number"], abbe)

    def test_mixed_sign_and_higher_eye_pick_the_index(self):
        # Steep meridian 3.00, not SE 2.00 (which would stay on 1.50).
        options, _rx = self._menu(sph_r="-1.00", cyl_r="-2.00")
        self.assertEqual(self._recommended(options)["metadata"]["index_value"], "1.61")

        # The left eye's 6.25 meridian outranks the right eye's 0.25.
        options, _rx = self._menu(
            sph_r="-0.25", cyl_r="0", sph_l="-5.00", cyl_l="-1.25")
        self.assertEqual(self._recommended(options)["metadata"]["index_value"], "1.74")

    def test_neighbor_tiers_and_the_150_exception(self):
        mild, _rx = self._menu(sph_r="0")
        self.assertEqual(
            [opt["metadata"]["index_value"] for opt in mild],
            ["1.50", "1.56", "1.61"])
        self.assertEqual(mild[0]["group"], "recommended")
        self.assertEqual(mild[1]["group"], "other_available")
        self.assertEqual(mild[2]["group"], "other_available")
        self.assertEqual(mild[1]["material"], "NK55")
        self.assertIsNone(mild[1]["abbe_number"])
        self.assertFalse(mild[1]["recommended"])
        self.assertNotIn("1.67", [opt["metadata"]["index_value"] for opt in mild])
        self.assertNotIn("1.74", [opt["metadata"]["index_value"] for opt in mild])

        mid, _rx = self._menu(sph_r="-3.00")
        self.assertEqual(
            [opt["metadata"]["index_value"] for opt in mid],
            ["1.56", "1.61", "1.67"])
        self.assertEqual(self._recommended(mid)["metadata"]["index_value"], "1.61")

        strong, _rx = self._menu(sph_r="-5.00")
        self.assertEqual(
            [opt["metadata"]["index_value"] for opt in strong],
            ["1.61", "1.67", "1.74"])
        self.assertEqual(self._recommended(strong)["metadata"]["index_value"], "1.67")

        high, _rx = self._menu(sph_r="-8.00")
        self.assertEqual(
            [opt["metadata"]["index_value"] for opt in high],
            ["1.67", "1.74"])
        self.assertEqual(self._recommended(high)["metadata"]["index_value"], "1.74")

    def test_only_one_badge_when_two_rows_share_the_index(self):
        LensIndexOption.objects.create(
            lens_type=self.lens_type, index_value=D("1.61"), tier="Driving",
            option_label="Driving - 1.61 Index", price=D("30.00"),
            sort_order=5, is_active=True)
        options, _rx = self._menu(sph_r="-3.00")
        winners = [opt for opt in options if opt["recommended"]]
        self.assertEqual(len(winners), 1)
        self.assertEqual(winners[0]["name"], "Popular - 1.61 Index")
        self.assertNotIn("Driving - 1.61 Index", [opt["name"] for opt in options])
        self.assertEqual(
            [opt["metadata"]["index_value"] for opt in options],
            ["1.56", "1.61", "1.67"])

    def test_unpriced_neighbor_is_hidden(self):
        # 1.56 has no cell at sphere -3. The 1.60 recommendation stays,
        # and 1.56 is not offered as the tier below.
        LensPriceCell.objects.filter(
            block__lens_index=D("1.56"), sphere=D("-3.00")).delete()
        options, _rx = self._menu(sph_r="-3.00")
        self.assertEqual(
            [opt["metadata"]["index_value"] for opt in options],
            ["1.61", "1.67"])
        self.assertEqual(self._recommended(options)["metadata"]["index_value"], "1.61")

    def test_quote_summary_cart_and_checkout_use_the_recommended_cell(self):
        options, rx = self._menu(sph_r="-3.00", cyl_r="0")
        winner = self._recommended(options)
        self.assertEqual(winner["metadata"]["index_value"], "1.61")
        # The menu's add-on is the catalog price. The charged price is the sheet cell.
        self.assertEqual(winner["add_on_price"], "19.95")

        quote = self.client.post("/api/lens-workflow/rx-quote/", {
            "od": {"sph": "-3.00", "cyl": "0"},
            "os": {"sph": "-3.00", "cyl": "0"},
            "lens_type_id": self.lens_type.id,
            "function_path_id": self.classic.id,
            "index_option_id": winner["id"],
            "price": "1.00",
        }, format="json")
        self.assertEqual(quote.status_code, 200, quote.content)
        self.assertEqual(quote.data["selection"]["lens_price"], "14.95")
        self.assertEqual(quote.data["selection"]["lens_index"], "1.60")
        self.assertEqual(quote.data["selection"]["catalog_index"], "1.61")
        self.assertEqual(quote.data["total_lens_price"], "14.95")
        self.assertFalse(quote.data["blocked"])

        summary = self.client.get("/api/lens-workflow/summary/", {
            "lens_type_id": self.lens_type.id,
            "function_path_id": self.classic.id,
            "index_option_id": winner["id"],
            "prescription_id": rx.id,
        })
        self.assertEqual(summary.status_code, 200, summary.content)
        self.assertEqual(summary.data["total_add_on_price"], "14.95")
        self.assertEqual(summary.data["quote"]["total_lens_price"], "14.95")
        self.assertEqual(summary.data["quote"]["selection"]["lens_price"], "14.95")

        frame = _frame("REC-100", D("100.00"))
        created = self.client.post("/api/order/createcompleteset", {
            "frame": {"sku": frame.sku},
            "lens_type": self.lens_type.id,
            "function_path": self.classic.id,
            "index_option": winner["id"],
            "prescription": {"id": rx.id},
            "sub_total": "1.00",
        }, format="json")
        self.assertEqual(created.status_code, 201, created.content)
        self.assertEqual(created.data["sub_total"], "114.95")

        added = self.client.post("/api/order/guest_cart", {
            "action": "add", "complete_set_id": created.data["id"],
        }, format="json")
        self.assertEqual(added.status_code, 200, added.content)
        cart = self.client.post("/api/order/guest_cart", {"action": "get"}, format="json")
        self.assertEqual(cart.status_code, 200, cart.content)
        self.assertEqual(D(str(cart.data["active_subtotal"])), D("114.95"))
        self.assertEqual(D(str(cart.data["eyeglasses_set"][0]["sub_total"])), D("114.95"))

        user = User.objects.create_user(username="buyer@example.com", password="test-pass-123")
        user.refresh_from_db()
        logged_in = APIClient()
        logged_in.defaults["HTTP_X_FORWARDED_PROTO"] = "https"
        logged_in.force_login(user)
        user.shopping_cart.eyeglasses_set.add(created.data["id"])
        address = Address.objects.create(customer=user, **_address_fields())
        pending = logged_in.post("/api/order/create_pending", {
            "complete_set_ids": [created.data["id"]],
            "address_id": address.id,
            "shipping_method": "Priority Shipping",
            "country": "United States",
            "email": "",
            "sub_total": "1.00",
        }, format="json")
        self.assertEqual(pending.status_code, 201, pending.content)
        self.assertEqual(D(str(pending.data["sub_total"])), D("114.95"))
        pair = CompleteSet.objects.get(pk=created.data["id"])
        self.assertEqual(pair.sub_total, D("114.95"))

    def test_max_cylinder_is_still_refused(self):
        response = self.client.post("/api/lens-workflow/rx-quote/", {
            "od": {"sph": "0", "cyl": "-6.25"},
            "os": {"sph": "0", "cyl": "0"},
            "lens_type_id": self.lens_type.id,
            "function_path_id": self.classic.id,
            "index_value": "1.50",
        }, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.data["block_reason"], "Max CYL is 6.00D")
        self.assertTrue(response.data["blocked"])
        self.assertIsNone(response.data["total_lens_price"])


class UnpricedTierTests(TestCase):
    """A missing or N cell walks up the ladder. Free Upgrade to 1.56 still counts."""

    def setUp(self):
        self.client = APIClient()
        self.client.defaults["HTTP_X_FORWARDED_PROTO"] = "https"
        self.lens_type = LensType.objects.create(
            code="SVD", label="Single Vision Distance",
            is_prescription_required=True,
            index_recommendation_category="SINGLE_VISION", is_active=True)
        self.classic = LensFunctionPath.objects.create(
            lens_type=self.lens_type, function_code="CLEAR", function_label="Classic",
            extra_price=D("0"), is_active=True)
        for index_value, price, tier, label in CATALOG:
            LensIndexOption.objects.create(
                lens_type=self.lens_type, index_value=D(index_value), tier=tier,
                option_label=label, price=D(price), is_active=True)

    def _menu(self):
        rx = PrescriptionInfo.objects.create(
            sphere_r=D("0"), cylinder_r=D("0"),
            sphere_l=D("0"), cylinder_l=D("0"))
        started = self.client.get("/api/lens-workflow/next/", {
            "current_step_code": "LENS_TYPE",
            "selected_option_id": self.lens_type.id,
        })
        menu = self.client.get("/api/lens-workflow/next/", {
            "current_step_code": "FUNCTION",
            "selected_option_id": self.classic.id,
            "selection_path": _selection_query(started.data["selection_path"]),
            "prescription_id": rx.id,
        })
        self.assertEqual(menu.status_code, 200, menu.content)
        return menu.data["options"], rx

    def test_walks_to_the_next_priced_tier_when_the_cell_is_n(self):
        blank = [["N", "N", "N"], ["N", "N", "N"], ["N", "N", "N"]]
        priced = [[19.95, 19.95, 19.95], [19.95, 19.95, 19.95], [19.95, 19.95, 19.95]]
        parsed = pt.parse_workbook(workbook({
            "Premium Lens": (
                [["Premium Lens (Conant)"], []]
                + block(index=1.5, prices=blank)
                + block(index=1.56, prices=priced)
                + block(index=1.6, prices=[[14.95, 14.95, 14.95]] * 3)
            ),
        }))
        self.assertTrue(parsed.ok, [e.message for e in parsed.errors])
        pt.apply_import(parsed, filename="walk.xlsx", file_bytes=b"x")

        options, _rx = self._menu()
        self.assertEqual(
            [opt["metadata"]["index_value"] for opt in options],
            ["1.56", "1.61"])
        winner = next(opt for opt in options if opt["recommended"])
        self.assertEqual(winner["metadata"]["index_value"], "1.56")
        self.assertEqual(winner["group"], "recommended")
        self.assertEqual(
            [opt["group"] for opt in options if not opt["recommended"]],
            ["other_available"])

    def test_free_upgrade_keeps_150_and_prices_it_from_156(self):
        blank = [["N", "N", "N"], ["N", "N", "N"], ["N", "N", "N"]]
        priced = [[19.95, 19.95, 19.95], [19.95, 19.95, 19.95], [19.95, 19.95, 19.95]]
        parsed = pt.parse_workbook(workbook({
            "Premium Lens": (
                [["Premium Lens (Conant)"], []]
                + block(index=1.5, prices=blank, note="Free Upgrade to 1.56")
                + block(index=1.56, prices=priced)
            ),
        }))
        self.assertTrue(parsed.ok, [e.message for e in parsed.errors])
        pt.apply_import(parsed, filename="upgrade.xlsx", file_bytes=b"x")

        options, rx = self._menu()
        # 1.60 is not on this sheet, so the 1.50 exception cannot show it.
        self.assertEqual(
            [opt["metadata"]["index_value"] for opt in options],
            ["1.50", "1.56"])
        winner = next(opt for opt in options if opt["recommended"])
        self.assertEqual(winner["metadata"]["index_value"], "1.50")

        quote = self.client.post("/api/lens-workflow/rx-quote/", {
            "od": {"sph": "0", "cyl": "0"},
            "os": {"sph": "0", "cyl": "0"},
            "lens_type_id": self.lens_type.id,
            "function_path_id": self.classic.id,
            "index_option_id": winner["id"],
        }, format="json")
        self.assertEqual(quote.status_code, 200, quote.content)
        self.assertTrue(quote.data["selection"]["free_upgrade"])
        self.assertEqual(quote.data["selection"]["lens_index"], "1.56")
        self.assertEqual(quote.data["total_lens_price"], "19.95")
        summary = self.client.get("/api/lens-workflow/summary/", {
            "lens_type_id": self.lens_type.id,
            "function_path_id": self.classic.id,
            "index_option_id": winner["id"],
            "prescription_id": rx.id,
        })
        self.assertEqual(summary.data["total_add_on_price"], "19.95")
        self.assertTrue(summary.data["quote"]["selection"]["free_upgrade"])

    def test_nothing_higher_means_the_index_step_is_empty(self):
        # Plano is priced at 1.50 only. Sphere -8.00 is on none of the
        # rungs, so the step explains that instead of returning a blank list.
        parsed = pt.parse_workbook(workbook({
            "Premium Lens": [["Premium Lens (Conant)"], []] + block(index=1.5),
        }))
        self.assertTrue(parsed.ok, [e.message for e in parsed.errors])
        pt.apply_import(parsed, filename="only150.xlsx", file_bytes=b"x")
        rx = PrescriptionInfo.objects.create(
            sphere_r=D("-8.00"), cylinder_r=D("0"),
            sphere_l=D("-8.00"), cylinder_l=D("0"))
        started = self.client.get("/api/lens-workflow/next/", {
            "current_step_code": "LENS_TYPE",
            "selected_option_id": self.lens_type.id,
        })
        menu = self.client.get("/api/lens-workflow/next/", {
            "current_step_code": "FUNCTION",
            "selected_option_id": self.classic.id,
            "selection_path": _selection_query(started.data["selection_path"]),
            "prescription_id": rx.id,
        })
        self.assertEqual(menu.status_code, 200, menu.content)
        self.assertEqual(menu.data["current_step"]["code"], "INDEX")
        self.assertEqual(menu.data["options"], [])
        self.assertEqual(
            menu.data["unavailable_reason"],
            "This prescription isn't available online yet. Please contact us.")
        self.assertEqual(
            menu.data["current_step"]["description"],
            menu.data["unavailable_reason"])


class RetiredIndexTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.client.defaults["HTTP_X_FORWARDED_PROTO"] = "https"
        self.lens_type = LensType.objects.create(
            code="SVD", label="Single Vision Distance",
            is_prescription_required=True,
            index_recommendation_category="SINGLE_VISION", is_active=True)
        self.classic = LensFunctionPath.objects.create(
            lens_type=self.lens_type, function_code="CLEAR", function_label="Classic",
            extra_price=D("0"), is_active=True)

    def _names(self):
        started = self.client.get("/api/lens-workflow/next/", {
            "current_step_code": "LENS_TYPE",
            "selected_option_id": self.lens_type.id,
        })
        menu = self.client.get("/api/lens-workflow/next/", {
            "current_step_code": "FUNCTION",
            "selected_option_id": self.classic.id,
            "selection_path": _selection_query(started.data["selection_path"]),
        })
        self.assertEqual(menu.status_code, 200, menu.content)
        return [opt["name"] for opt in menu.data["options"]]

    def test_migration_deactivates_by_name_and_index_without_deleting(self):
        popular = LensIndexOption.objects.create(
            lens_type=self.lens_type, tier="Popular", option_label="Popular - 1.61 Index",
            index_value=D("1.61"), price=D("19.95"), is_active=True)
        driving = LensIndexOption.objects.create(
            lens_type=self.lens_type, tier="Driving", option_label="Driving - 1.61 Index",
            index_value=D("1.61"), price=D("19.95"), is_active=True)
        safety = LensIndexOption.objects.create(
            lens_type=self.lens_type, tier="Safety",
            option_label="Safety - 1.59 Index (Polycarbonate)",
            index_value=D("1.59"), price=D("19.95"), is_active=True)
        elite = LensIndexOption.objects.create(
            lens_type=self.lens_type, tier="Elite", option_label="Elite - 1.71 Index",
            index_value=D("1.71"), price=D("59.95"), is_active=True)
        # Same words at a different index, or the index without the name, stay.
        other = LensIndexOption.objects.create(
            lens_type=self.lens_type, tier="Driving", option_label="Driving - 1.67 Index",
            index_value=D("1.67"), price=D("39.95"), is_active=True)
        plain_159 = LensIndexOption.objects.create(
            lens_type=self.lens_type, tier="Basic", option_label="Basic - 1.59 Index",
            index_value=D("1.59"), price=D("19.95"), is_active=True)

        self.assertIn("Driving - 1.61 Index", self._names())
        self.assertNotIn("Safety - 1.59 Index (Polycarbonate)", self._names())
        self.assertNotIn("Elite - 1.71 Index", self._names())

        from django.apps import apps
        deactivate_retired_index_options(apps, None)

        for row in (driving, safety, elite):
            row.refresh_from_db()
            self.assertFalse(row.is_active)
            self.assertTrue(LensIndexOption.objects.filter(pk=row.pk).exists())
        popular.refresh_from_db()
        other.refresh_from_db()
        plain_159.refresh_from_db()
        self.assertTrue(popular.is_active)
        self.assertTrue(other.is_active)
        self.assertTrue(plain_159.is_active)

        names = self._names()
        self.assertIn("Popular - 1.61 Index", names)
        self.assertNotIn("Driving - 1.61 Index", names)
        self.assertNotIn("Safety - 1.59 Index (Polycarbonate)", names)
        self.assertNotIn("Elite - 1.71 Index", names)

    def test_seed_lists_do_not_contain_the_retired_tiers(self):
        for table in (INDEX_TIERS_SVD, INDEX_TIERS_FULL, INDEX_TIERS_NARROW):
            blob = " ".join(f"{row[0]} {row[2]} {row[3]}" for row in table).lower()
            self.assertNotIn("driving", blob)
            self.assertNotIn("safety", blob)
            self.assertNotIn("elite", blob)
            self.assertNotIn("1.59", blob)
            self.assertNotIn("1.71", blob)


class BlueLightCoatingTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.client.defaults["HTTP_X_FORWARDED_PROTO"] = "https"
        self.lens_type = LensType.objects.create(
            code="SVD", label="Single Vision Distance",
            is_prescription_required=True,
            index_recommendation_category="SINGLE_VISION", is_active=True)
        self.classic = LensFunctionPath.objects.create(
            lens_type=self.lens_type, function_code="CLEAR", function_label="Classic",
            color_required=False, extra_price=D("0"), is_active=True, sort_order=10)
        self.blue = LensFunctionPath.objects.create(
            lens_type=self.lens_type, function_code="BLUE_LIGHT_FILTERING",
            function_label="Blue Light Filtering", color_required=False,
            extra_price=D("9.95"), is_active=True, sort_order=20)
        self.photo = LensFunctionPath.objects.create(
            lens_type=self.lens_type, function_code="PHOTOCHROMIC",
            function_label="Photochromic", color_required=True,
            extra_price=D("29.95"), is_active=True, sort_order=30)
        self.sun = LensFunctionPath.objects.create(
            lens_type=self.lens_type, function_code="SUN", function_label="Sun",
            sun_type="", color_required=False, extra_price=D("9.95"),
            is_active=True, sort_order=40)
        self.solid = LensFunctionPath.objects.create(
            lens_type=self.lens_type, function_code="SUN", function_label="Solid",
            sun_type="SOLID", color_required=True, extra_price=D("9.95"),
            is_active=True, sort_order=41)
        self.photo_color = LensColorOption.objects.create(
            function_path=self.photo, color_name="Grey", extra_price=D("0"),
            available_index_values=["1.50", "1.56", "1.61", "1.67", "1.74"],
            is_active=True)
        self.sun_color = LensColorOption.objects.create(
            function_path=self.solid, color_name="50% Gray", extra_price=D("0"),
            available_index_values=["1.50", "1.56", "1.61", "1.67", "1.74"],
            is_active=True)
        LensIndexOption.objects.create(
            lens_type=self.lens_type, tier="Basic", option_label="Basic - 1.50 Index",
            index_value=D("1.50"), price=D("4.95"), is_active=True)
        LensCoating.objects.create(
            code="ANTI_SCRATCH", label="Anti-scratch", price=D("0"),
            is_included=True, is_active=True, sort_order=10)
        self.blue_coat = LensCoating.objects.create(
            code="BLUE_LIGHT_FILTERING", label="Blue Light Filtering",
            price=D("9.95"), is_included=False, is_active=True, sort_order=20)
        LensCoating.objects.create(
            code="OLEOPHOBIC", label="Oleophobic", price=D("4.95"),
            is_included=False, is_active=True, sort_order=30)

    def _next(self, step, selected, previous=None):
        path = [] if previous is None else previous.data["selection_path"]
        params = {
            "current_step_code": step,
            "selected_option_id": selected,
            "selection_path": _selection_query(path),
        }
        if previous is not None and previous.data.get("total_steps") is not None:
            params["current_step_index"] = previous.data["step_index"]
            params["total_steps"] = previous.data["total_steps"]
        response = self.client.get("/api/lens-workflow/next/", params)
        self.assertEqual(response.status_code, 200, response.content)
        return response

    def _coating_step(self, function, *, tint=None, color=None):
        step = self._next("LENS_TYPE", self.lens_type.id)
        step = self._next("FUNCTION", function.id, step)
        if tint is not None:
            self.assertEqual(step.data["current_step"]["code"], "TINT_TYPE")
            step = self._next("TINT_TYPE", tint.id, step)
        if color is not None:
            self.assertEqual(step.data["current_step"]["code"], "COLOR")
            step = self._next("COLOR", color.id, step)
        self.assertEqual(step.data["current_step"]["code"], "INDEX")
        index_id = step.data["options"][0]["id"]
        step = self._next("INDEX", index_id, step)
        self.assertEqual(step.data["current_step"]["code"], "COATING")
        return step

    def _codes(self, step):
        return [opt["code"] for opt in step.data["options"]]

    def test_blue_light_coating_is_hidden_only_after_the_blue_light_function(self):
        classic = self._coating_step(self.classic)
        self.assertIn("BLUE_LIGHT_FILTERING", self._codes(classic))
        self.assertIn("ANTI_SCRATCH", self._codes(classic))
        self.assertIn("OLEOPHOBIC", self._codes(classic))

        photo = self._coating_step(self.photo, color=self.photo_color)
        self.assertIn("BLUE_LIGHT_FILTERING", self._codes(photo))

        sun = self._coating_step(self.sun, tint=self.solid, color=self.sun_color)
        self.assertIn("BLUE_LIGHT_FILTERING", self._codes(sun))

        blue = self._coating_step(self.blue)
        self.assertNotIn("BLUE_LIGHT_FILTERING", self._codes(blue))
        self.assertIn("ANTI_SCRATCH", self._codes(blue))
        self.assertIn("OLEOPHOBIC", self._codes(blue))

        rejected = self.client.get("/api/lens-workflow/next/", {
            "current_step_code": "COATING",
            "selected_option_ids": str(self.blue_coat.id),
            "selection_path": _selection_query(blue.data["selection_path"]),
        })
        self.assertEqual(rejected.status_code, 400, rejected.content)
        self.assertIn("can't be selected again", rejected.data["detail"])

        accepted = self.client.get("/api/lens-workflow/next/", {
            "current_step_code": "COATING",
            "selected_option_ids": str(self.blue_coat.id),
            "selection_path": _selection_query(classic.data["selection_path"]),
        })
        self.assertEqual(accepted.status_code, 200, accepted.content)
        self.assertTrue(accepted.data["is_complete"])


def _priced_block(index, rx, spheres, cyls, priced):
    """One clear block. `priced` is a set of (sphere, cylinder) Decimals."""
    rows = [HEADER + [float(cyl) for cyl in cyls]]
    for n, sph in enumerate(spheres):
        if n == 0:
            meta = ["", "", "", None, rx, "Clear", "N", "N", "N", float(index), "material"]
        else:
            meta = [None] * 11
        cells = [
            9.95 if (sph, cyl) in priced else "N"
            for cyl in cyls
        ]
        rows.append(meta + [float(sph)] + cells)
    return rows


# Mirrors price2_fixed.xlsx: distance/bifocal/progressive spheres are minus
# only, high indexes omit mild powers, and plus power exists only on Reading.
_SVD_SPHERES = [D(v) for v in ("0", "-0.25", "-2.00", "-3.00", "-5.00", "-6.25", "-8.00")]
_SVD_CYLS = [D(v) for v in ("0", "-1.25", "-3.50")]
_SVD_PRICED = {
    D("1.50"): {(D("0"), D("0")), (D("-0.25"), D("0"))},
    D("1.56"): {(D("0"), D("0")), (D("-0.25"), D("0")), (D("-2.00"), D("0"))},
    D("1.60"): {
        (D("0"), D("0")), (D("-0.25"), D("0")), (D("-2.00"), D("0")),
        (D("-3.00"), D("0")), (D("-5.00"), D("0")), (D("-5.00"), D("-1.25")),
    },
    D("1.67"): {
        (D("-2.00"), D("0")), (D("-5.00"), D("0")), (D("-5.00"), D("-1.25")),
        (D("-6.25"), D("0")), (D("-8.00"), D("0")),
    },
    D("1.74"): {
        (D("-5.00"), D("-1.25")), (D("-6.25"), D("0")), (D("-8.00"), D("0")),
    },
}


def _shaped_like_the_real_sheet():
    rows = [["Premium Lens (Conant)"], []]
    for rx in ("Single Vision Distance", "Bifocal", "Progressive"):
        for index, priced in _SVD_PRICED.items():
            rows += _priced_block(index, rx, _SVD_SPHERES, _SVD_CYLS, priced)
    rows += _priced_block(
        D("1.60"), "Reading",
        [D("0"), D("1.00"), D("2.50")],
        [D("0"), D("3.50")],
        {(D("1.00"), D("0")), (D("2.50"), D("0"))},
    )
    parsed = pt.parse_workbook(workbook({"Premium Lens": rows}))
    if not parsed.ok:
        raise AssertionError([error.message for error in parsed.errors])
    pt.apply_import(parsed, filename="shaped.xlsx", file_bytes=b"x")


class RealSheetGapTests(TestCase):
    """Holes in the real price sheet: plus power, mixed eyes, high progressive."""

    @classmethod
    def setUpTestData(cls):
        _shaped_like_the_real_sheet()
        cls.catalog = {}
        for code, category in (
            ("SVD", "SINGLE_VISION"),
            ("READING", "SINGLE_VISION"),
            ("PROGRESSIVE", "BIFOCAL_PROGRESSIVE"),
            ("BIFOCAL", "BIFOCAL_PROGRESSIVE"),
        ):
            lens_type = LensType.objects.create(
                code=code, label=code, is_prescription_required=True,
                index_recommendation_category=category, is_active=True)
            function = LensFunctionPath.objects.create(
                lens_type=lens_type, function_code="CLEAR", function_label="Classic",
                extra_price=D("0"), is_active=True)
            for index_value, price, tier, label in CATALOG:
                LensIndexOption.objects.create(
                    lens_type=lens_type, index_value=D(index_value), tier=tier,
                    option_label=label, price=D(price), is_active=True)
            cls.catalog[code] = (lens_type, function)

    def setUp(self):
        self.client = APIClient()
        self.client.defaults["HTTP_X_FORWARDED_PROTO"] = "https"

    def _menu(self, code, *, sph_r, cyl_r=0, sph_l=None, cyl_l=0):
        if sph_l is None:
            sph_l = sph_r
            cyl_l = cyl_r
        lens_type, function = self.catalog[code]
        rx = PrescriptionInfo.objects.create(
            sphere_r=D(str(sph_r)), cylinder_r=D(str(cyl_r)),
            sphere_l=D(str(sph_l)), cylinder_l=D(str(cyl_l)))
        started = self.client.get("/api/lens-workflow/next/", {
            "current_step_code": "LENS_TYPE",
            "selected_option_id": lens_type.id,
        })
        menu = self.client.get("/api/lens-workflow/next/", {
            "current_step_code": "FUNCTION",
            "selected_option_id": function.id,
            "selection_path": _selection_query(started.data["selection_path"]),
            "prescription_id": rx.id,
        })
        self.assertEqual(menu.status_code, 200, menu.content)
        self.assertEqual(menu.data["current_step"]["code"], "INDEX")
        return menu

    def _indexes(self, menu):
        return [opt["metadata"]["index_value"] for opt in menu.data["options"]]

    def _assert_unavailable(self, menu):
        self.assertEqual(menu.data["options"], [])
        self.assertEqual(
            menu.data["unavailable_reason"],
            "This prescription isn't available online yet. Please contact us.")
        self.assertEqual(
            menu.data["current_step"]["description"],
            menu.data["unavailable_reason"])

    def test_plus_power_svd_is_absent_from_the_real_sheet(self):
        # The lookup asks for Single Vision Distance. The file has plus
        # spheres only on Reading / Clear, so this is not a sign-mapping bug.
        with Path("lens_workflow/data/price2_fixed.xlsx").open("rb") as handle:
            parsed = pt.parse_workbook(handle)
        self.assertTrue(parsed.ok, [error.message for error in parsed.errors])
        for blocks in parsed.blocks.values():
            for block_data in blocks:
                if block_data.prescription_type != "Single Vision Distance":
                    continue
                self.assertFalse(
                    any(sphere > 0 for sphere in block_data.sphere_axis),
                    block_data.label())
        reading_plus = [
            block_data for blocks in parsed.blocks.values() for block_data in blocks
            if block_data.prescription_type == "Reading"
            and block_data.lens_type == "Clear"
            and block_data.lens_index == D("1.60")
            and (D("1.00"), D("0")) in block_data.prices
            and (D("2.50"), D("0")) in block_data.prices
        ]
        self.assertTrue(reading_plus)

    def test_plus_power_svd_explains_the_empty_menu(self):
        for power in ("1.00", "2.50"):
            menu = self._menu("SVD", sph_r=power)
            self._assert_unavailable(menu)
        # The same plus powers are priced when the lens type is Reading.
        reading = self._menu("READING", sph_r="1.00")
        self.assertEqual(
            [opt["metadata"]["index_value"] for opt in reading.data["options"]
             if opt["recommended"]],
            ["1.61"])

    def test_mixed_sign_plus_sphere_is_not_on_the_distance_grid(self):
        # S +1.00 C -3.50 keeps sphere +1.00. Distance grids have no plus row.
        menu = self._menu("SVD", sph_r="1.00", cyl_r="-3.50")
        self._assert_unavailable(menu)

    def test_higher_eye_walks_down_to_the_index_that_prices_both_eyes(self):
        # OS steep meridian is 6.25, which asks for 1.74. 1.74 and 1.67 have
        # no cell at OD -0.25. 1.60 prices both eyes.
        menu = self._menu(
            "SVD", sph_r="-0.25", cyl_r="0", sph_l="-5.00", cyl_l="-1.25")
        self.assertEqual(self._indexes(menu), ["1.61"])
        self.assertTrue(menu.data["options"][0]["recommended"])
        self.assertNotIn("unavailable_reason", menu.data)

    def test_progressive_and_bifocal_high_power_offer_174(self):
        self.assertIn("1.74", [row[0] for row in INDEX_TIERS_NARROW])
        for code in ("PROGRESSIVE", "BIFOCAL"):
            for power in ("-6.25", "-8.00"):
                menu = self._menu(code, sph_r=power)
                self.assertEqual(self._indexes(menu), ["1.67", "1.74"], f"{code} {power}")
                winner = next(opt for opt in menu.data["options"] if opt["recommended"])
                self.assertEqual(winner["metadata"]["index_value"], "1.74")

    def test_blank_eye_is_plano(self):
        created = self.client.post("/api/prescriptions/", {
            "sphere_r": "-3.00",
            "sphere_l": None,
            "cylinder_l": "",
        }, format="json")
        self.assertEqual(created.status_code, 201, created.content)
        self.assertEqual(created.data["sphere_l"], "0.00")
        self.assertEqual(created.data["cylinder_l"], "0.00")
        lens_type, function = self.catalog["SVD"]
        started = self.client.get("/api/lens-workflow/next/", {
            "current_step_code": "LENS_TYPE",
            "selected_option_id": lens_type.id,
        })
        menu = self.client.get("/api/lens-workflow/next/", {
            "current_step_code": "FUNCTION",
            "selected_option_id": function.id,
            "selection_path": _selection_query(started.data["selection_path"]),
            "prescription_id": created.data["id"],
        })
        self.assertEqual(menu.status_code, 200, menu.content)
        self.assertEqual(self._indexes(menu), ["1.61"])
        self.assertTrue(menu.data["options"][0]["recommended"])


class ShopperCopyTests(TestCase):
    def test_seed_copy_has_no_internal_wording(self):
        banned = (
            "sheet", "priced as", "abbe", "cr-39", "mr-8", "mr-7", "mr-174",
            "tier below", "recommendation",
        )
        for text in INDEX_RATIONALE.values():
            lowered = text.lower()
            for word in banned:
                self.assertNotIn(word, lowered, text)
        notes = importlib.import_module(
            "lens_workflow.migrations.0015_shopper_notes_and_high_index"
        ).SHOPPER_NOTES
        self.assertEqual(notes, dict(INDEX_RATIONALE))

    def test_migration_rewrites_notes_and_adds_174(self):
        progressive = LensType.objects.create(
            code="PROGRESSIVE", label="Progressives", is_prescription_required=True,
            index_recommendation_category="BIFOCAL_PROGRESSIVE", is_active=True)
        bifocal = LensType.objects.create(
            code="BIFOCAL", label="Bifocals", is_prescription_required=True,
            index_recommendation_category="BIFOCAL_PROGRESSIVE", is_active=True)
        svd = LensType.objects.create(
            code="SVD", label="Single Vision Distance", is_prescription_required=True,
            index_recommendation_category="SINGLE_VISION", is_active=True)
        LensIndexOption.objects.create(
            lens_type=svd, tier="Premium", option_label="Premium - 1.74 Index",
            index_value=D("1.74"), price=D("79.95"),
            notes="MR-174, Abbe 32. The sheet prices this lens as 1.74.",
            is_active=True)
        LensIndexOption.objects.create(
            lens_type=progressive, tier="Popular", option_label="Popular - 1.61 Index",
            index_value=D("1.61"), price=D("19.95"),
            notes="The sheet prices this lens as 1.60.",
            is_active=True)
        migration = importlib.import_module(
            "lens_workflow.migrations.0015_shopper_notes_and_high_index")
        from django.apps import apps
        migration.rewrite_index_notes(apps, None)
        migration.add_progressive_and_bifocal_174(apps, None)
        popular = LensIndexOption.objects.get(lens_type=progressive, index_value=D("1.61"))
        self.assertEqual(popular.notes, INDEX_RATIONALE["1.61"])
        self.assertNotIn("sheet", popular.notes.lower())
        for lens_type in (progressive, bifocal):
            row = LensIndexOption.objects.get(
                lens_type=lens_type, index_value=D("1.74"), tier="Premium")
            self.assertTrue(row.is_active)
            self.assertEqual(row.price, D("79.95"))
            self.assertEqual(row.notes, INDEX_RATIONALE["1.74"])

    def test_reseed_writes_shopper_copy(self):
        call_command("seed_shopping_flow_data")
        notes = list(LensIndexOption.objects.filter(is_active=True).values_list("notes", flat=True))
        self.assertTrue(notes)
        for note in notes:
            lowered = (note or "").lower()
            self.assertNotIn("sheet", lowered)
            self.assertNotIn("priced as", lowered)
            self.assertNotIn("abbe", lowered)
            self.assertNotIn("tier below", lowered)


class SeededIdCollisionTests(TestCase):
    """Fresh seed: lens type 1, Classic function 1, and an index sharing the Blue Light id."""

    def setUp(self):
        self.client = APIClient()
        self.client.defaults["HTTP_X_FORWARDED_PROTO"] = "https"
        for model in (
            LensColorOption, LensIndexOption, LensFunctionPath, LensCoating,
            LensIndexRecommendationRule, LensReaderStrength, LensType,
        ):
            model.objects.all().delete()
        statements = connection.ops.sequence_reset_sql(no_style(), [
            LensType, LensFunctionPath, LensIndexOption, LensColorOption,
            LensCoating, LensReaderStrength, LensIndexRecommendationRule,
        ])
        with connection.cursor() as cursor:
            for statement in statements:
                cursor.execute(statement)
        call_command("seed_shopping_flow_data")

    def _next(self, step, selected, previous=None, *, step_index=None, total_steps=None):
        params = {
            "current_step_code": step,
            "selected_option_id": selected,
            "selection_path": _selection_query(
                [] if previous is None else previous.data["selection_path"]),
        }
        if step_index is not None:
            params["current_step_index"] = step_index
            params["total_steps"] = total_steps
        elif previous is not None and previous.data.get("total_steps") is not None:
            params["current_step_index"] = previous.data["step_index"]
            params["total_steps"] = previous.data["total_steps"]
        response = self.client.get("/api/lens-workflow/next/", params)
        self.assertEqual(response.status_code, 200, response.content)
        return response

    def _coating(self, function, *, tint=None, color=None, index_id=None):
        step = self._next("LENS_TYPE", function.lens_type_id)
        self.assertEqual(step.data["selection_path"], [
            {"step": "LENS_TYPE", "id": function.lens_type_id},
        ])
        step = self._next("FUNCTION", function.id, step)
        self.assertIn(
            {"step": "FUNCTION", "id": function.id},
            step.data["selection_path"])
        if tint is not None:
            self.assertEqual(step.data["current_step"]["code"], "TINT_TYPE")
            step = self._next("TINT_TYPE", tint.id, step)
        if color is not None:
            self.assertEqual(step.data["current_step"]["code"], "COLOR")
            step = self._next("COLOR", color.id, step)
        self.assertEqual(step.data["current_step"]["code"], "INDEX")
        if index_id is None:
            index_id = step.data["options"][0]["id"]
        else:
            self.assertIn(index_id, [opt["id"] for opt in step.data["options"]])
        step = self._next("INDEX", index_id, step)
        self.assertEqual(step.data["current_step"]["code"], "COATING")
        return step

    def test_classic_keeps_blue_light_when_ids_collide(self):
        svd = LensType.objects.get(code="SVD")
        classic = LensFunctionPath.objects.get(
            lens_type=svd, function_code="CLEAR", sun_type="")
        blue = LensFunctionPath.objects.get(
            lens_type=svd, function_code="BLUE_LIGHT_FILTERING", sun_type="")
        photo = LensFunctionPath.objects.get(
            lens_type=svd, function_code="PHOTOCHROMIC", sun_type="")
        sun = LensFunctionPath.objects.get(
            lens_type=svd, function_code="SUN", sun_type="")
        solid = LensFunctionPath.objects.get(
            lens_type=svd, function_code="SUN", sun_type="SOLID")
        # The collision a fresh database actually produces.
        self.assertEqual(svd.id, classic.id)
        colliding_index = LensIndexOption.objects.get(pk=blue.id, lens_type=svd)
        self.assertNotEqual(colliding_index.id, classic.id)

        classic_step = self._coating(classic, index_id=colliding_index.id)
        codes = [opt["code"] for opt in classic_step.data["options"]]
        self.assertIn("BLUE_LIGHT_FILTERING", codes)
        self.assertIn(
            {"step": "FUNCTION", "id": classic.id},
            classic_step.data["selection_path"])
        self.assertIn(
            {"step": "INDEX", "id": colliding_index.id},
            classic_step.data["selection_path"])
        blue_coat = LensCoating.objects.get(code="BLUE_LIGHT_FILTERING")
        accepted = self.client.get("/api/lens-workflow/next/", {
            "current_step_code": "COATING",
            "selected_option_ids": str(blue_coat.id),
            "selection_path": _selection_query(classic_step.data["selection_path"]),
        })
        self.assertEqual(accepted.status_code, 200, accepted.content)
        self.assertTrue(accepted.data["is_complete"])

        photo_color = LensColorOption.objects.filter(function_path=photo).first()
        photo_step = self._coating(photo, color=photo_color)
        self.assertIn(
            "BLUE_LIGHT_FILTERING",
            [opt["code"] for opt in photo_step.data["options"]])

        sun_color = LensColorOption.objects.filter(function_path=solid).first()
        sun_step = self._coating(sun, tint=solid, color=sun_color)
        self.assertIn(
            "BLUE_LIGHT_FILTERING",
            [opt["code"] for opt in sun_step.data["options"]])

        blue_step = self._coating(blue, index_id=colliding_index.id)
        self.assertNotIn(
            "BLUE_LIGHT_FILTERING",
            [opt["code"] for opt in blue_step.data["options"]])
        rejected = self.client.get("/api/lens-workflow/next/", {
            "current_step_code": "COATING",
            "selected_option_ids": str(blue_coat.id),
            "selection_path": _selection_query(blue_step.data["selection_path"]),
        })
        self.assertEqual(rejected.status_code, 400, rejected.content)
        self.assertIn("can't be selected again", rejected.data["detail"])
