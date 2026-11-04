import io
from decimal import Decimal

import openpyxl
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from . import price_table as pt
from .models import LensPriceBlock, LensPriceCell, LensPriceImport

HEADER = ["Recommended SE", "Limitation S", "Limitation C", "Rationale", "Prescription Type",
          "Lens Type", "Color", "Depth", "Coating", "Index", "Material", "Sphere/Cylinder"]


def workbook(sheets):
    """sheets: {sheet name: [row lists]} -> BytesIO of an .xlsx"""
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for name, rows in sheets.items():
        ws = wb.create_sheet(name)
        for r in rows:
            ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def block(index=1.5, material="CR-39", rx="Single Vision Distance", lens="Clear",
          color="N", depth="N", coating="N", prices=None, note=None, cyl=("Plano", -0.25, -0.5)):
    """A small valid block: 3 sphere rows x len(cyl) cylinder columns."""
    prices = prices or [[9.95, "N", 9.95], [9.95, "N", 9.95], ["N", "N", "N"]]
    rows = [HEADER + list(cyl)]
    spheres = ["Plano", -0.25, -0.5]
    for n, (sph, pr) in enumerate(zip(spheres, prices)):
        meta = ["0 ~ -1.50D", "S<=-1.00", "C<=-1.00", None, rx, lens, color, depth, coating, index, material] if n == 0 \
            else [note if n == 1 else None] + [None] * 10
        rows.append(meta + [sph] + pr)
    return rows


class ParseTests(TestCase):
    def test_valid_file(self):
        r = pt.parse_workbook(workbook({"Premium Lens": [["Premium Lens (Conant)"], []] + block()}))
        self.assertTrue(r.ok, [e.message for e in r.errors])
        b = r.blocks["premium"][0]
        self.assertEqual(b.lens_index, Decimal("1.50"))
        self.assertEqual(b.prices[(Decimal("0.00"), Decimal("0.00"))], Decimal("9.95"))
        self.assertNotIn((Decimal("0.00"), Decimal("-0.25")), b.prices)   # N = no lens

    def test_not_an_xlsx(self):
        r = pt.parse_workbook(io.BytesIO(b"definitely not excel"))
        self.assertFalse(r.ok)
        self.assertIn("not a valid .xlsx", r.errors[0].message)

    def test_unknown_sheet(self):
        r = pt.parse_workbook(workbook({"Sheet1": block()}))
        self.assertEqual(r.errors[0].sheet, "Sheet1")
        self.assertIn("Unknown sheet", r.errors[0].message)

    def test_no_header_rows(self):
        r = pt.parse_workbook(workbook({"Premium Lens": [["just", "text"]]}))
        self.assertIn("No block headers", r.errors[0].message)

    def test_cell_problems_name_the_cell(self):
        rows = block(prices=[[9.95, "x", 9.95], [9.95, None, -5], ["N", "N", "N"]])
        r = pt.parse_workbook(workbook({"Premium Lens": rows}))
        cells = {e.cell: e.message for e in r.errors}
        self.assertIn('Price must be a number', cells["N2"])        # "x" at row 2, col N
        self.assertIn("Empty cell", cells["N3"])
        self.assertIn("greater than 0", cells["O3"])

    def test_wrong_header_and_bad_index(self):
        rows = block(index="abc")
        r = pt.parse_workbook(workbook({"Economic Lens": rows}))
        self.assertIn("Index must be a number", {e.cell: e.message for e in r.errors}["J2"])
        rows = block()
        rows[0][4] = "Rx"          # stale / wrong header text
        rows[0][7] = "Coating Main"   # the old layout's column name
        r = pt.parse_workbook(workbook({"Economic Lens": rows}))
        msgs = {e.cell: e.message for e in r.errors}
        self.assertIn('Unknown column header "Rx"', msgs["E1"])
        self.assertIn('Unknown column header "Coating Main"', msgs["H1"])

    def test_columns_are_found_by_name_so_rationale_can_be_deleted(self):
        rows = block()
        rows = [[v for i, v in enumerate(row) if i != 3] for row in rows]    # drop column D
        r = pt.parse_workbook(workbook({"Premium Lens": rows}))
        self.assertTrue(r.ok, [e.message for e in r.errors])
        self.assertEqual(r.blocks["premium"][0].lens_index, Decimal("1.50"))
        self.assertEqual(r.blocks["premium"][0].prices[(Decimal("0"), Decimal("0"))], Decimal("9.95"))

    def test_empty_color_depth_coating_is_a_warning(self):
        r = pt.parse_workbook(workbook({"Premium Lens": block(color=None)}))
        self.assertTrue(r.ok)
        self.assertTrue(any("Color is empty" in w.message for w in r.warnings))
        self.assertEqual(r.blocks["premium"][0].color, "N")

    def test_missing_required_text(self):
        rows = block(lens=None)
        r = pt.parse_workbook(workbook({"Premium Lens": rows}))
        self.assertTrue(any("Lens Type is empty" in e.message for e in r.errors))

    def test_duplicate_lens(self):
        r = pt.parse_workbook(workbook({"Premium Lens": block() + block()}))
        self.assertTrue(any("more than once" in e.message for e in r.errors))

    def test_price_row_without_sphere_is_an_error_but_text_row_a_warning(self):
        rows = block()
        rows.append([None] * 11 + [None, 5.0, "N", "N"])
        r = pt.parse_workbook(workbook({"Premium Lens": rows}))
        self.assertTrue(any("no sphere power" in e.message for e in r.errors))
        rows = block()
        rows.append([None] * 11 + [None, "Conant", "Conant", "Conant"])
        r = pt.parse_workbook(workbook({"Premium Lens": rows}))
        self.assertTrue(r.ok)
        self.assertTrue(any("is ignored" in w.message for w in r.warnings))

    def test_warning_for_cylinder_hole(self):
        hole = [[9.95, "N", 9.95], [9.95, "N", 9.95], ["N", "N", "N"]]
        cheap = [[5.00, 5.00, 5.00], [5.00, 5.00, 5.00], ["N", "N", "N"]]
        rows = block(index=1.5, prices=hole) + block(index=1.6, prices=cheap)
        r = pt.parse_workbook(workbook({"Premium Lens": rows}))
        self.assertTrue(r.ok)
        text = " | ".join(w.message for w in r.warnings)
        self.assertIn("has no price on any row", text)

    def test_missing_sheet_is_a_warning(self):
        r = pt.parse_workbook(workbook({"Premium Lens": block()}))
        self.assertTrue(any("Economic Lens" in w.message for w in r.warnings))

    def test_index_price_inversion_is_not_flagged(self):
        # A higher index costing less than a lower one is normal (stock vs custom lenses)
        cheap = [[5.00, 5.00, 5.00], [5.00, 5.00, 5.00], ["N", "N", "N"]]
        rows = block(index=1.5) + block(index=1.6, prices=cheap)
        r = pt.parse_workbook(workbook({"Premium Lens": rows}))
        self.assertFalse(any("costs" in w.message for w in r.warnings))


class ImportExportTests(TestCase):
    def sample(self):
        return workbook({
            "Premium Lens": [["Premium Lens (Conant)"], []] + block(note="Free Upgrade to 1.56")
                            + block(index=1.56, material="NK55", prices=[[9.95, 9.95, 9.95]] * 3),
            "Economic Lens": [["Economic Lens (Value)"], []] + block(index=1.6, depth="30%, 50%"),
        })

    def test_apply_replaces_only_sheets_in_file(self):
        pt.apply_import(pt.parse_workbook(self.sample()), filename="a.xlsx", file_bytes=b"x")
        self.assertEqual(LensPriceBlock.objects.filter(tier="premium").count(), 2)
        self.assertEqual(LensPriceBlock.objects.filter(tier="economic").count(), 1)
        only_premium = workbook({"Premium Lens": block(index=1.67)})
        pt.apply_import(pt.parse_workbook(only_premium), filename="b.xlsx", file_bytes=b"y")
        self.assertEqual(list(LensPriceBlock.objects.filter(tier="premium").values_list("lens_index", flat=True)),
                         [Decimal("1.67")])
        self.assertEqual(LensPriceBlock.objects.filter(tier="economic").count(), 1)   # untouched
        self.assertEqual(LensPriceImport.objects.count(), 2)

    def test_round_trip(self):
        pt.apply_import(pt.parse_workbook(self.sample()), filename="a.xlsx", file_bytes=b"x")
        exported = pt.build_workbook()
        again = pt.parse_workbook(io.BytesIO(exported))
        self.assertTrue(again.ok, [e.message for e in again.errors])
        original = pt.parse_workbook(self.sample())
        for tier in ("premium", "economic"):
            a, b = original.blocks[tier], again.blocks[tier]
            self.assertEqual(len(a), len(b))
            for x, y in zip(a, b):
                self.assertEqual((x.key, x.prices, x.sphere_axis, x.cylinder_axis, x.note, x.material),
                                 (y.key, y.prices, y.sphere_axis, y.cylinder_axis, y.note, y.material))

    def test_price_lookup(self):
        pt.apply_import(pt.parse_workbook(self.sample()), filename="a.xlsx", file_bytes=b"x")
        args = ("premium", "Single Vision Distance", "Clear", "N", "N", "N", Decimal("1.50"))
        self.assertEqual(pt.price_for(*args, Decimal("0"), Decimal("0")), Decimal("9.95"))
        self.assertIsNone(pt.price_for(*args, Decimal("0"), Decimal("-0.25")))     # N
        self.assertIsNone(pt.price_for(*args, Decimal("-9"), Decimal("0")))        # off the grid


class AdminTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_superuser("boss@example.com", "pw")
        self.client.defaults["HTTP_X_FORWARDED_PROTO"] = "https"   # settings redirect plain http
        self.client.force_login(self.admin)
        self.base = "admin:lens_workflow_lenspriceblock_"

    def upload(self, buf, action):
        buf.seek(0)
        buf.name = "prices.xlsx"
        return self.client.post(reverse(self.base + "import_prices"),
                                {"xlsx_file": buf, "action": action})

    def test_changelist_has_buttons_and_no_generic_import(self):
        pt.apply_import(pt.parse_workbook(workbook({"Premium Lens": block()})), filename="a.xlsx")
        html = self.client.get(reverse(self.base + "changelist")).content.decode()
        self.assertIn("Download current prices", html)
        self.assertIn("Replace prices from Excel", html)
        self.assertNotIn("import-excel", html)

    def test_export_download(self):
        pt.apply_import(pt.parse_workbook(workbook({"Premium Lens": block()})), filename="a.xlsx")
        r = self.client.get(reverse(self.base + "export_prices"))
        self.assertEqual(r.status_code, 200)
        self.assertIn("spreadsheetml", r["Content-Type"])
        wb = openpyxl.load_workbook(io.BytesIO(r.content))
        self.assertEqual(wb.sheetnames, ["Premium Lens", "Economic Lens"])

    def test_bad_file_changes_nothing_and_lists_cells(self):
        pt.apply_import(pt.parse_workbook(workbook({"Premium Lens": block(index=1.5)})), filename="a.xlsx")
        bad = block(index=1.6, prices=[[9.95, "oops", 9.95], [9.95, "N", 9.95], ["N", "N", "N"]])
        r = self.upload(workbook({"Premium Lens": bad}), "apply")
        self.assertContains(r, "Nothing was changed")
        self.assertContains(r, "N2")
        self.assertEqual(LensPriceBlock.objects.get().lens_index, Decimal("1.50"))

    def test_check_only_does_not_apply_and_apply_does(self):
        good = workbook({"Premium Lens": block(index=1.67)})
        self.assertContains(self.upload(good, "check"), "has no errors")
        self.assertEqual(LensPriceBlock.objects.count(), 0)
        self.assertContains(self.upload(workbook({"Premium Lens": block(index=1.67)}), "apply"), "Prices replaced")
        self.assertEqual(LensPriceBlock.objects.get().lens_index, Decimal("1.67"))

    def test_non_xlsx_name_rejected(self):
        f = io.BytesIO(b"x")
        f.name = "prices.csv"
        r = self.client.post(reverse(self.base + "import_prices"), {"xlsx_file": f, "action": "apply"})
        self.assertContains(r, "ending in .xlsx")

    def test_staff_without_permission_is_turned_away(self):
        User = get_user_model()
        staff = User.objects.create_user("staff@example.com", "pw", is_staff=True)
        self.client.force_login(staff)
        r = self.client.get(reverse(self.base + "export_prices"))
        self.assertEqual(r.status_code, 302)
