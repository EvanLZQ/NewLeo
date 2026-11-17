"""Lens pricing v2 (round-3 spec /round3/REPORT3.md).

* SheetTests / EngineTests: no database; parse the real price_v2.xlsx once.
* ImporterTests / ApiTests / CartTests: database (versions, endpoints,
  CompleteSet pricing, re-pricing in open carts, frozen paid orders).

Expected prices come from the price file and the report's §3.5 examples.
"""
import io
import os
import tempfile
from decimal import Decimal as D

import openpyxl
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIClient

from lens_workflow.models import LensLine, LensPricingSettings, PriceBlock, PriceTableVersion
from lens_workflow.pricing_v2 import config as C
from lens_workflow.pricing_v2 import engine as E
from lens_workflow.pricing_v2 import importer, sheet, store

DATA = os.path.join(os.path.dirname(__file__), "data")
XLSX = os.path.join(DATA, "price_v2.xlsx")
OVERRIDES_YAML = os.path.join(DATA, "price_overrides.yaml")
SHEETS = {"economic lens": "economic", "premium lens": "premium"}
P648 = [{"cell": "Premium Lens!D649", "from": 1.56, "to": 1.5, "source": "boss Q3"}]

_PARSED = {}


def parsed(overrides=P648):
    key = repr(overrides)
    if key not in _PARSED:
        with open(XLSX, "rb") as f:
            _PARSED[key] = sheet.parse_workbook(f, SHEETS, C.defaults(), overrides)
    return _PARSED[key]


def catalog():
    r = parsed()
    return E.Catalog([E.block_from_parsed(b, i) for i, b in enumerate(r.blocks)],
                     [E.Line("economic", "Economic", 10), E.Line("premium", "Premium (Conant)", 20)])


def eye(s, c="0", axis=None):
    return E.EyeRx(D(s), D(c), axis)


CLEAR = E.Selection("CLEAR")
BLUE = E.Selection("CLEAR", coating="BLUE")


def sun(color, depth, tint="SOLID", coating="N"):
    return E.Selection("SUN", tint=tint, color=color, depth=depth, coating=coating)


def cards(q):
    """{line: (recommended index, {index: price})}"""
    return {c.line: (str(c.recommended_index), {str(o.index): str(o.price) for o in c.options})
            for c in q.cards}


# ── sheet ────────────────────────────────────────────────────────────────────

class SheetTests(SimpleTestCase):
    def test_limitation_forms(self):
        P = sheet.parse_limitation
        self.assertEqual(P("S≤-4.00", "S"), (D("0"), D("4.00"), False))
        self.assertEqual(P("S≤+2.00", "S"), (D("0"), D("2.00"), False))
        self.assertEqual(P("S≤±8.00", "S"), (D("0"), D("8.00"), False))
        self.assertEqual(P("-4.00≤S≤-8.00", "S"), (D("4.00"), D("8.00"), False))   # written backwards
        self.assertEqual(P("C≤‑1.50", "C"), (D("0"), D("1.50"), False))   # U+2011 hyphen
        self.assertEqual(P("C>-2.00", "C"), (D("2.00"), sheet.BIG, True))
        with self.assertRaises(ValueError):
            P("S≈4", "S")
        with self.assertRaises(ValueError):
            P("C≤-1.00", "S")

    def test_steep_label_depth(self):
        self.assertEqual(sheet.parse_steep("2.25 ~ 4.00 D"), (D("2.25"), D("4.00")))
        self.assertEqual(sheet.parse_steep("6.25 D ~ Above"), (D("6.25"), sheet.BIG))
        self.assertIsNone(sheet.parse_steep("Gradient and Sun/Tinted lens ..."))
        self.assertEqual(sheet.parse_label("Free Upgrade to Index 1.56"), (C.LABEL_FREE_UPGRADE, D("1.56")))
        self.assertEqual(sheet.parse_label("Free Upgrade to 1.56"), (C.LABEL_FREE_UPGRADE, D("1.56")))
        self.assertEqual(sheet.parse_label("Recommended"), (C.LABEL_RECOMMENDED, None))
        self.assertEqual(sheet.parse_depths("0.8"), [80])
        self.assertEqual(sheet.parse_depths("30%, 50%, 80%"), [30, 50, 80])
        self.assertEqual(sheet.parse_depths("N"), [])

    def test_p648_without_override_is_refused(self):
        r = parsed(overrides=[])
        self.assertFalse(r.ok)
        self.assertEqual(len(r.errors), 1)
        self.assertIn("defined more than once (row 648, row 657)", r.errors[0].message)

    def test_price_v2_with_override(self):
        r = parsed()
        self.assertTrue(r.ok, [str(e) for e in r.errors])
        self.assertEqual(len(r.blocks), 194)
        self.assertEqual(len(r.overrides_applied), 1)
        by_line = {ln: sum(1 for b in r.blocks if b.line == ln) for ln in ("economic", "premium")}
        self.assertEqual(by_line, {"economic": 124, "premium": 70})
        p648 = next(b for b in r.blocks if b.sheet == "Premium Lens" and b.source_row == 648)
        self.assertEqual(p648.lens_index, D("1.50"))
        self.assertEqual(p648.material, "CR-39")

    def test_override_mismatch_and_obsolete(self):
        bad = [{"cell": "Premium Lens!D649", "from": 1.67, "to": 1.5, "source": "x"}]
        with open(XLSX, "rb") as f:
            r = sheet.parse_workbook(f, SHEETS, C.defaults(), bad)
        self.assertTrue(any("override expects" in e.message for e in r.errors))
        stale = [{"cell": "Premium Lens!D658", "from": 1.67, "to": 1.56, "source": "x"}]
        with open(XLSX, "rb") as f:
            r = sheet.parse_workbook(f, SHEETS, C.defaults(), P648 + stale)
        self.assertTrue(r.ok)
        self.assertTrue(any("override not needed" in w.message for w in r.warnings))

    def test_columns_by_header_name_and_unknown_sheet(self):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Economic Lens"
        # Columns deliberately in another order than price_v2.
        ws.append(["Index", "Steep Meridian", "Limitation S", "Limitation C", "Recommendation",
                   "Prescription Type", "Lens Type", "Color", "Depth", "Coating", "Material",
                   "Sphere/Cylinder", "Plano", -0.25])
        ws.append([1.5, "0 ~ 2.00 D", "S≤-1.00", "C≤-1.00", "Recommended", "Single Vision Nearsighted",
                   "Clear", "N", "N", "N", "CR-39", "Plano", 4.95, 5.95])
        ws.append([None] * 11 + [-0.25, 6.95, "N"])
        wb.create_sheet("Notes")
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        r = sheet.parse_workbook(buf, SHEETS, C.defaults(), [])
        self.assertTrue(r.ok, [str(e) for e in r.errors])
        b = r.blocks[0]
        self.assertEqual((b.rx_type, b.lens_type, b.coating, b.lens_index), ("SV_NEAR", "CLEAR", "N", D("1.50")))
        self.assertEqual(b.grid, {(D("0.00"), D("0.00")): D("4.95"), (D("0.00"), D("0.25")): D("5.95"),
                                  (D("0.25"), D("0.00")): D("6.95")})
        self.assertTrue(any(w.sheet == "Notes" and "ignored" in w.message for w in r.warnings))

    def test_bad_values_are_errors(self):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Economic Lens"
        ws.append(["Steep Meridian", "Limitation S", "Limitation C", "Index", "Recommendation",
                   "Prescription Type", "Lens Type", "Color", "Depth", "Coating", "Material",
                   "Sphere/Cylinder", "Plano"])
        ws.append(["0 ~ 2.00 D", "S≤ten", "C≤-1.00", 1.5, "Maybe", "Single Vision Nearsighted",
                   "Clear", "Rainbow", "N", "N", "CR-39", "Plano", "abc"])
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        r = sheet.parse_workbook(buf, SHEETS, C.defaults(), [])
        msgs = " | ".join(e.message for e in r.errors)
        self.assertIn('unknown Color "Rainbow"', msgs)
        self.assertIn("cannot read Limitation S", msgs)
        self.assertIn("price must be a number or N", msgs)


# ── engine ───────────────────────────────────────────────────────────────────

class EngineTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.cat = catalog()
        cls.cfg = C.defaults()

    def q(self, category, od, os_, sel, **cfg):
        return E.quote(self.cat, dict(self.cfg, **cfg), category, od, os_, sel)

    # 1.1 prescription
    def test_transpose_plus_cylinder(self):
        self.assertEqual(E.transpose(eye("-1.00", "+0.50", 90)), (D("-0.50"), D("-0.50"), 180))
        self.assertEqual(E.transpose(eye("+2.00", "+1.00", 10)), (D("3.00"), D("-1.00"), 100))
        self.assertEqual(E.transpose(eye("-2.00", "-1.00", 45)), (D("-2.00"), D("-1.00"), 45))

    def test_classification(self):
        self.assertEqual(E.pricing_eye(eye("-1"), E.SV).rx_type, "SV_NEAR")
        self.assertEqual(E.pricing_eye(eye("+1"), E.SV).rx_type, "SV_FAR")
        self.assertEqual(E.pricing_eye(eye("0", "-1"), E.SV).rx_type, "SV_NEAR")     # plano + cyl
        self.assertEqual(E.pricing_eye(eye("+1", "-3"), E.SV).rx_type, "SV_FAR")     # mixed (Q1=A)
        self.assertEqual(E.pricing_eye(eye("-1", "+2"), E.SV).rx_type, "SV_FAR")     # +1 / -2 after transposing
        self.assertEqual(E.pricing_eye(eye("+1", "-3"), E.SV).m, D("2.00"))
        self.assertEqual(E.pricing_eye(eye("-3"), E.PROGRESSIVE).rx_type, "PROGRESSIVE")

    # 3.5 P648
    def test_p648_premium_sun(self):
        self.assertEqual(cards(self.q(E.SV, eye("-1", "-1"), eye("-1", "-1"), sun("green", 50)))["premium"],
                         ("1.50", {"1.50": "124.95", "1.56": "134.95"}))
        self.assertEqual(cards(self.q(E.SV, eye("-1.5"), eye("-1.5"), sun("green", 50)))["premium"][0], "1.56")
        self.assertEqual(cards(self.q(E.SV, eye("-1.5"), eye("-1.5"), sun("green", 50)))["premium"][1]["1.56"],
                         "134.95")
        self.assertEqual(cards(self.q(E.SV, eye("-1", "-2"), eye("-1", "-2"), sun("green", 50)))["premium"],
                         ("1.60", {"1.60": "149.95"}))

    # 3.5 Q2
    def test_q2_one_near_one_far(self):
        c = cards(self.q(E.SV, eye("-3"), eye("+1"), CLEAR))
        self.assertEqual(c["economic"][0], "1.60")
        self.assertEqual(c["economic"][1]["1.60"], "14.95")
        self.assertEqual(c["premium"][1]["1.60"], "34.95")

    def test_q2_fallback_when_higher_index_not_common(self):
        q = self.q(E.SV, eye("-3.25", "-1"), eye("+0.25"), CLEAR)
        c = cards(q)
        self.assertEqual(c["economic"], ("1.60", {"1.60": "14.95"}))
        self.assertEqual(c["premium"], ("1.60", {"1.60": "34.95"}))
        self.assertEqual(q.card("economic").fallback, "down")

    def test_q2_no_common_index(self):
        q = self.q(E.SV, eye("-0.25"), eye("+4.25"), CLEAR)
        self.assertEqual(q.cards, [])
        self.assertEqual(q.as_dict()["unavailable_reason"], E.REASON_NO_RX)

    def test_q2_equal_meridian_uses_farsighted_eye(self):
        c = cards(self.q(E.SV, eye("-0.5"), eye("+0.5"), CLEAR))
        self.assertEqual(c["premium"], ("1.50", {"1.50": "24.95", "1.56": "29.95"}))

    def test_each_eye_prices_from_own_table(self):
        q = self.q(E.SV, eye("-3"), eye("+1"), CLEAR)
        opt = q.card("premium").option("1.60")
        tables = {b["eye"]: b["row"] for b in opt.blocks}
        self.assertNotEqual(tables["od"], tables["os"])   # near block vs far block

    def test_mixed_astigmatism_uses_far_table(self):
        c = cards(self.q(E.SV, eye("+1", "-3"), eye("+1", "-3"), CLEAR))
        self.assertEqual(c, {"economic": ("1.60", {"1.60": "24.95"})})   # Premium far: no cyl > 2.00

    # Limitation switch
    def test_limitation_switch(self):
        on = cards(self.q(E.PROGRESSIVE, eye("-1", "-2"), eye("-1", "-2"), CLEAR))
        self.assertEqual(on, {"economic": ("1.60", {"1.60": "64.95"})})
        off = cards(self.q(E.PROGRESSIVE, eye("-1", "-2"), eye("-1", "-2"), CLEAR, enforce_limitation=False))
        self.assertIn("premium", off)
        self.assertIn("1.56", off["economic"][1])

    # Free Upgrade
    def test_free_upgrade_hides_150_and_charges_its_price(self):
        q = self.q(E.SV, eye("-1"), eye("-1"), sun("gray", 50))
        econ = q.card("economic")
        self.assertNotIn(D("1.50"), [o.index for o in econ.options])
        self.assertTrue(econ.option("1.56").free_upgrade)
        # Q9: polarized 1.50 = 39.95, 1.56 = 44.95 → 1.56 shown, 39.95 charged
        pol = self.q(E.SV, eye("-1"), eye("-1"), E.Selection("SUN", tint="POLARIZED", color="brown"))
        o = pol.card("economic").option("1.56")
        self.assertEqual((o.price, o.free_upgrade, o.charged_index), (D("39.95"), True, D("1.50")))
        self.assertIsNone(pol.card("premium"))

    # Colours / depth / gradient
    def test_dedicated_color_block_wins(self):
        def econ(sel):
            return cards(self.q(E.SV, eye("-1"), eye("-1"), sel))["economic"][1]
        self.assertEqual(econ(sun("gray", 80))["1.50"], "9.95")
        self.assertEqual(econ(sun("brown", 80))["1.50"], "9.95")
        self.assertEqual(econ(sun("green", 80))["1.56"], "39.95")
        self.assertEqual(econ(sun("gray", 50))["1.56"], "39.95")

    def test_gradient_80_gray_policy(self):
        def econ(**cfg):
            return cards(self.q(E.SV, eye("-1"), eye("-1"), sun("gray", 80, "GRADIENT"), **cfg))["economic"]
        self.assertEqual(econ(), ("1.56", {"1.56": "39.95", "1.60": "59.95"}))      # default (question 3 → B)
        self.assertEqual(econ(gradient_ignore_dedicated_depths=[])[1]["1.50"], "9.95")  # option A

    def test_gradient_availability(self):
        g = sun("gray", 50, "GRADIENT")
        prog = cards(self.q(E.PROGRESSIVE, eye("-1"), eye("-1"), g))
        self.assertEqual(list(prog), ["economic"])           # Premium progressive: no tint prices
        self.assertEqual(prog["economic"][1]["1.50"], "89.95")
        self.assertEqual(list(cards(self.q(E.BIFOCAL, eye("-1"), eye("-1"), g))), ["economic"])
        self.assertEqual(list(cards(self.q(E.SV, eye("+1"), eye("+1"), g))), ["economic"])
        self.assertEqual(sorted(cards(self.q(E.SV, eye("-1"), eye("-1"), g))), ["economic", "premium"])

    def test_polarized_and_mirrored_colors(self):
        sel = E.selections_for(self.cat, self.cfg, E.SV)
        pol = sorted({s.color for s in sel if s.tint == "POLARIZED"})
        mir = sorted({s.color for s in sel if s.tint == "MIRRORED"})
        self.assertEqual(pol, ["black-gray", "brown", "gray-green", "night-vision-yellow"])
        self.assertEqual(len(mir), 8)
        self.assertNotIn("night-vision-yellow", mir)
        nvy = self.q(E.SV, eye("-1"), eye("-1"), E.Selection("SUN", tint="POLARIZED", color="night-vision-yellow"))
        brown = self.q(E.SV, eye("-1"), eye("-1"), E.Selection("SUN", tint="POLARIZED", color="brown"))
        self.assertEqual(cards(nvy), cards(brown))            # Q10=B: same price

    def test_photochromic_pink_only_where_priced(self):
        pink = E.Selection("PHOTOCHROMIC", color="pink")
        self.assertTrue(self.q(E.SV, eye("-1"), eye("-1"), pink).cards)
        self.assertFalse(self.q(E.SV, eye("+1"), eye("+1"), pink).cards)     # Q12=A
        self.assertFalse(self.q(E.PROGRESSIVE, eye("-1"), eye("-1"), pink).cards)

    def test_max_cyl(self):
        q = self.q(E.SV, eye("-1", "-6.25"), eye("-1"), CLEAR)
        self.assertEqual(q.blocked_reason, "Max CYL is 6.00D")

    def test_neighbors_are_common_indexes(self):
        q = self.q(E.SV, eye("-5"), eye("-5"), CLEAR)
        econ = q.card("economic")
        self.assertEqual(econ.recommended_index, D("1.67"))
        # 1.60 is limited to |S| <= 4.00, so only 1.74 sits next to 1.67
        self.assertEqual([str(o.index) for o in econ.options], ["1.67", "1.74"])
        q = self.q(E.SV, eye("-1.75", "-1"), eye("-1.75", "-1"), CLEAR)
        econ = q.card("economic")
        self.assertEqual(econ.recommended_index, D("1.60"))
        # Economic 1.67 is limited to 4.00 <= |S| <= 8.00, so no upper neighbour here
        self.assertEqual([str(o.index) for o in econ.options], ["1.56", "1.60"])
        prem = self.q(E.SV, eye("-3"), eye("-3"), CLEAR).card("premium")
        self.assertEqual([str(o.index) for o in prem.options], ["1.60", "1.67"])
        self.assertTrue(prem.option("1.67").material)

    def test_premium_materials(self):
        q = self.q(E.SV, eye("-3"), eye("-3"), CLEAR)
        mats = {str(o.index): o.material for o in q.card("premium").options}
        self.assertEqual(mats.get("1.60"), "MR-8")
        self.assertTrue(mats.get("1.67", "").startswith("MR-7"))

    def test_non_rx(self):
        c = cards(self.q(E.NON_RX, eye("-9"), eye("+9"), CLEAR))   # Rx ignored
        self.assertEqual(c["economic"][1]["1.56"], "4.95")

    # Readers (Economic Clear / Blue Light, 18 powers)
    def test_readers_table(self):
        expect = {"0.25": ("9.95", "14.95"), "1.00": ("9.95", "14.95"), "1.25": ("9.95", "14.95"),
                  "1.75": ("9.95", "14.95"), "2.00": ("14.95", "19.95"), "2.25": ("14.95", "19.95"),
                  "4.00": ("14.95", "19.95"), "4.25": ("24.95", "29.95"), "4.50": ("24.95", "29.95")}
        powers = E.reader_powers(self.cfg)
        self.assertEqual(len(powers), 18)
        for p in powers:
            opts = E.quote_reader(self.cat, self.cfg, p)
            self.assertEqual([o["coating"] for o in opts], ["N", "BLUE"], p)
            self.assertTrue(all(o["line"] == "economic" for o in opts))
            if str(p) in expect:
                self.assertEqual((str(opts[0]["price"]), str(opts[1]["price"])), expect[str(p)], p)
        with self.assertRaises(E.SelectionError):
            E.quote_reader(self.cat, self.cfg, D("4.75"))

    def test_readers_premium_config(self):
        opts = E.quote_reader(self.cat, dict(self.cfg, reader_line="premium"), D("2.25"))
        self.assertEqual([str(o["price"]) for o in opts], ["34.95", "44.95"])

    def test_selection_validation(self):
        for bad in (E.Selection("SUN", tint="SOLID", color="gray"),          # no depth
                    E.Selection("SUN", tint="POLARIZED", color="brown", coating="BLUE"),
                    E.Selection("PHOTOCHROMIC"), E.Selection("GLASS")):
            with self.assertRaises(E.SelectionError):
                E.validate_selection(bad)

    def test_available_selections_drive_the_steps(self):
        a = E.available_selections(self.cat, self.cfg, E.SV, eye("-1"), eye("-1"))
        types = {s.lens_type for s in a}
        self.assertEqual(types, {"CLEAR", "PHOTOCHROMIC", "SUN"})
        self.assertIn(sun("gray", 80, "GRADIENT"), a)
        self.assertEqual(a[E.Selection("SUN", tint="MIRRORED", color="rv-red")], ["economic"])
        far = E.available_selections(self.cat, self.cfg, E.SV, eye("+1"), eye("+1"))
        self.assertFalse(any(s.tint in ("POLARIZED", "MIRRORED") for s in far))
        self.assertEqual(E.available_selections(self.cat, self.cfg, E.SV, eye("-1", "-7"), eye("-1")), {})


# ── database: import / versions ──────────────────────────────────────────────

def _bytes():
    with open(XLSX, "rb") as f:
        return f.read()


def _modified_bytes(changes):
    """price_v2 with {"Sheet!N4": value} changes applied."""
    wb = openpyxl.load_workbook(XLSX)
    for ref, value in changes.items():
        name, addr = ref.split("!")
        wb[name][addr] = value
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


class _Imported(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.v1, cls.report1 = importer.import_file(_bytes(), "price_v2.xlsx", P648, label="price_v2")
        importer.activate(cls.v1, user="test")

    def setUp(self):
        store.clear_cache()


class ImporterTests(_Imported):
    def test_import_creates_active_version(self):
        self.v1.refresh_from_db()
        self.assertEqual(self.v1.status, "active")
        self.assertEqual(self.v1.blocks.count(), 194)
        self.assertEqual(self.report1["diff"]["summary"], {"added": 194})
        self.assertEqual(len(self.report1["overrides_applied"]), 1)

    def test_refused_without_override_and_nothing_saved(self):
        n = PriceTableVersion.objects.count()
        with self.assertRaises(importer.ImportRefused) as cm:
            importer.import_file(_bytes(), "price_v2.xlsx", [])
        self.assertTrue(cm.exception.report["errors"])
        self.assertEqual(PriceTableVersion.objects.count(), n)

    def test_dry_run_saves_nothing_and_diffs(self):
        n = PriceBlock.objects.count()
        data = _modified_bytes({"Economic Lens!N4": 5.95, "Premium Lens!N4": 12.95})
        result, report = importer.dry_run(data, "price_v3.xlsx", P648)
        self.assertTrue(result.ok)
        self.assertEqual(PriceBlock.objects.count(), n)
        d = report["diff"]
        self.assertEqual(d["summary"], {"changed": 2})
        econ = next(p for p in d["products"] if p["product"].startswith("economic"))
        self.assertEqual((econ["old_prices"], econ["new_prices"], econ["max_increase"]), (["4.95"], ["5.95"], "1.00"))
        prem = next(c for c in d["cells"] if c["product"].startswith("premium"))
        self.assertEqual((prem["sphere"], prem["cylinder"], prem["old"], prem["new"]), ("0.00", "0.00", "14.95", "12.95"))
        with tempfile.TemporaryDirectory() as tmp:
            importer.write_report(report, tmp)
            self.assertTrue(set(os.listdir(tmp)) >= {"report.json", "problems.csv", "summary.md",
                                                     "price_changes_products.csv", "price_changes_cells.csv"})
            with open(os.path.join(tmp, "price_changes_cells.csv"), encoding="utf-8-sig") as f:
                self.assertEqual(len(f.read().strip().splitlines()), 3)

    def test_activate_and_rollback(self):
        v2, _ = importer.import_file(_modified_bytes({"Economic Lens!N24": 10.95}), "price_v3.xlsx", P648)
        self.assertEqual(v2.status, "draft")
        self.assertEqual(store.active_version(), self.v1)
        importer.activate(v2)
        self.assertEqual(store.active_version().pk, v2.pk)
        self.v1.refresh_from_db()
        self.assertEqual(self.v1.status, "archived")
        cat = store.active_catalog()
        q = E.quote(cat, C.get_config(), E.SV, eye("0"), eye("0"), CLEAR)
        self.assertEqual(q.card("economic").option("1.60").price, D("10.95"))
        back = importer.rollback()
        self.assertEqual(back.pk, self.v1.pk)
        q = E.quote(store.active_catalog(), C.get_config(), E.SV, eye("0"), eye("0"), CLEAR)
        self.assertEqual(q.card("economic").option("1.60").price, D("9.95"))
        self.assertEqual(PriceTableVersion.objects.count(), 2)                 # nothing deleted

    def test_only_one_active(self):
        v2, _ = importer.import_file(_bytes(), "again.xlsx", P648)
        with self.assertRaises(IntegrityError), transaction.atomic():
            PriceTableVersion.objects.filter(pk=v2.pk).update(status="active")

    def test_inactive_line_is_not_sold(self):
        LensLine.objects.filter(code="premium").update(is_active=False)
        q = E.quote(store.active_catalog(), C.get_config(), E.SV, eye("-1"), eye("-1"), CLEAR)
        self.assertEqual([c.line for c in q.cards], ["economic"])

    def test_settings_row_overrides_defaults(self):
        s = LensPricingSettings.load()
        s.enforce_limitation = False
        s.reader_line = "premium"
        s.overrides = {"neighbor_count": 2}
        s.save()
        cfg = C.get_config()
        self.assertEqual((cfg["enforce_limitation"], cfg["reader_line"], cfg["neighbor_count"]),
                         (False, "premium", 2))

    def test_management_commands(self):
        out = io.StringIO()
        call_command("import_lens_prices_v2", XLSX, "--overrides", OVERRIDES_YAML, "--dry-run",
                     "--quiet-warnings", stdout=out)
        self.assertIn("Dry run: nothing was saved.", out.getvalue())
        out = io.StringIO()
        call_command("import_lens_prices_v2", XLSX, "--overrides", OVERRIDES_YAML, "--quiet-warnings",
                     "--label", "cmd", stdout=out)
        vid = PriceTableVersion.objects.get(label="cmd").pk
        call_command("lens_price_version", "activate", str(vid), stdout=io.StringIO())
        self.assertEqual(store.active_version().pk, vid)
        call_command("lens_price_version", "rollback", stdout=io.StringIO())
        self.assertEqual(store.active_version().pk, self.v1.pk)
        out = io.StringIO()
        call_command("lens_price_version", "list", stdout=out)
        self.assertIn("cmd", out.getvalue())


# ── database: API ────────────────────────────────────────────────────────────

class ApiTests(_Imported):
    def setUp(self):
        super().setUp()
        self.c = APIClient()
        self.c.defaults["HTTP_X_FORWARDED_PROTO"] = "https"

    def post(self, url, body):
        return self.c.post(f"/api/lens-workflow/v2/{url}/", body, format="json")

    def test_config(self):
        r = self.c.get("/api/lens-workflow/v2/config/")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.data["pricing_active"])
        self.assertEqual([c["code"] for c in r.data["categories"]],
                         ["SINGLE_VISION", "BIFOCAL", "PROGRESSIVE", "READERS", "NON_RX"])
        self.assertEqual((r.data["add"]["min"], r.data["add"]["max"]), ("0.75", "3.50"))
        self.assertEqual(len(r.data["readers"]["powers"]), 18)
        self.assertEqual([x["code"] for x in r.data["lines"]], ["economic", "premium"])

    def test_selections_and_quote(self):
        rx = {"category": "SINGLE_VISION", "od": {"sph": "-3.00"}, "os": {"sph": "+1.00"}}
        r = self.post("selections", rx)
        self.assertEqual(r.status_code, 200, r.data)
        self.assertTrue(any(s["lens_type"] == "CLEAR" and s["coating"] == "N" for s in r.data["selections"]))
        grad = [s for s in r.data["selections"] if s["tint"] == "GRADIENT" and s["color"] == "gray" and s["depth"] == 50]
        self.assertEqual(grad[0]["swatch"], "sun_gradient-50_gray.png")
        r = self.post("quote", dict(rx, selection={"lens_type": "CLEAR", "coating": "N"}))
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual([c["line"] for c in r.data["cards"]], ["economic", "premium"])
        self.assertEqual(r.data["cards"][0]["options"][0]["price"], "14.95")
        self.assertEqual(r.data["pricing_rx"]["os"]["table"], "SV_FAR")

    def test_add_validation(self):
        base = {"category": "PROGRESSIVE", "selection": {"lens_type": "CLEAR"}}
        bad = self.post("quote", dict(base, od={"sph": "-1", "add": "4.00"}, os={"sph": "-1", "add": "2.00"}))
        self.assertEqual(bad.status_code, 400)
        self.assertIn("ADD must be between +0.75 and +3.50", bad.data["detail"])
        ok = self.post("quote", dict(base, od={"sph": "-1", "add": "2.00"}, os={"sph": "-1", "add": "2.00"}))
        self.assertEqual(ok.status_code, 200)
        sv = self.post("quote", {"category": "SINGLE_VISION", "od": {"sph": "-1"}, "os": {"sph": "-1"},
                                 "selection": {"lens_type": "CLEAR"}})
        self.assertEqual(sv.status_code, 200)    # no ADD for single vision

    def test_unavailable_and_bad_requests(self):
        r = self.post("quote", {"category": "SINGLE_VISION", "od": {"sph": "-0.25"}, "os": {"sph": "+4.25"},
                                "selection": {"lens_type": "CLEAR"}})
        self.assertEqual((r.data["cards"], r.data["unavailable_reason"]), ([], E.REASON_NO_RX))
        r = self.post("quote", {"category": "SINGLE_VISION", "od": {"sph": "x"}, "os": {"sph": "1"},
                                "selection": {"lens_type": "CLEAR"}})
        self.assertEqual(r.status_code, 400)
        r = self.post("selections", {"category": "SINGLE_VISION", "od": {"sph": "-1", "cyl": "-6.50"},
                                     "os": {"sph": "-1"}})
        self.assertEqual(r.data["unavailable_reason"], "Max CYL is 6.00D")

    def test_reader_quote(self):
        r = self.post("reader-quote", {"power": "2.00"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual([(o["label"], o["price"]) for o in r.data["options"]],
                         [("Clear", "14.95"), ("Blue Light Filtering", "19.95")])
        self.assertEqual(self.post("reader-quote", {"power": "5.00"}).status_code, 400)

    def test_no_active_version(self):
        PriceTableVersion.objects.update(status="archived")
        store.clear_cache()
        self.assertEqual(self.post("reader-quote", {"power": "2.00"}).status_code, 503)
        self.assertFalse(self.c.get("/api/lens-workflow/v2/config/").data["pricing_active"])


# ── database: cart / order ───────────────────────────────────────────────────

class CartTests(_Imported):
    def setUp(self):
        super().setUp()
        from Order.tests import _frame
        self.frame = _frame("V2-TEST-1", "20.00")
        self.c = APIClient(enforce_csrf_checks=False)
        self.c.defaults["HTTP_X_FORWARDED_PROTO"] = "https"

    def _rx(self, **kw):
        from Prescription.testing import rx_via_api
        base = dict(sphere_r=-3.0, sphere_l=1.0, cylinder_r=0, cylinder_l=0, pd_l=31.5, pd_r=31.5)
        base.update(kw)
        return rx_via_api(self.c, **base)

    def _create(self, selection, rx=None):
        body = {"frame": {"sku": self.frame.sku}, "lens_selection": selection}
        if rx is not None:
            body["prescription"] = {"id": rx.id}
        return self.c.post("/api/order/createcompleteset", body, format="json")

    def test_cart_item_priced_from_active_version(self):
        rx = self._rx()
        sel = {"category": "SINGLE_VISION", "lens_type": "CLEAR", "coating": "N", "line": "premium", "index": "1.60"}
        r = self._create(sel, rx)
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.data["sub_total"], "54.95")                    # 20.00 frame + 34.95
        self.assertEqual(r.data["lens_type"], "Single Vision")
        self.assertIn("Premium (Conant", r.data["lens_summary"])
        from Order.models import CompleteSet
        cs = CompleteSet.objects.get(pk=r.data["id"])
        self.assertEqual((cs.lens_line, cs.price_version_id), ("premium", self.v1.pk))
        self.assertEqual(cs.pricing_rx["os"]["table"], "SV_FAR")
        self.assertEqual(cs.price_snapshot["unit_price"], "34.95")
        self.assertEqual({b["eye"] for b in cs.price_snapshot["blocks"]}, {"od", "os"})
        self.assertEqual(str(cs.prescription.sphere_r), "-3.00")         # original Rx kept

    def test_open_cart_reprices_after_new_version_but_paid_order_does_not(self):
        rx = self._rx(sphere_r=0, sphere_l=0)
        sel = {"category": "SINGLE_VISION", "lens_type": "CLEAR", "coating": "N", "line": "economic", "index": "1.56"}
        paid = self._create(sel, rx).data["id"]
        open_ = self._create(sel, rx).data["id"]
        from Order.models import CompleteSet, OrderInfo
        order = OrderInfo.objects.create(email="a@example.com", payment_status="PAID", refound_amount=0)
        cs = CompleteSet.objects.get(pk=paid)
        cs.order = order
        cs.save()
        self.assertEqual(str(cs.sub_total), "24.95")                   # 20 + 4.95
        # 1.56 here is a Free Upgrade from 1.50: it costs min(1.50, 1.56) → change both
        v2, _ = importer.import_file(_modified_bytes({"Economic Lens!N4": 7.95, "Economic Lens!N14": 7.95}),
                                     "v3.xlsx", P648)
        importer.activate(v2)
        o = CompleteSet.objects.get(pk=open_)
        o.save()
        self.assertEqual(str(o.sub_total), "27.95")                    # Q15=A: open cart takes new price
        self.assertEqual(o.price_version_id, v2.pk)
        p = CompleteSet.objects.get(pk=paid)
        p.save()
        self.assertEqual(str(p.sub_total), "24.95")                    # paid order keeps its price
        self.assertEqual(p.price_version_id, self.v1.pk)

    def test_option_no_longer_offered(self):
        rx = self._rx(sphere_r=-0.25, sphere_l=4.25)
        r = self._create({"category": "SINGLE_VISION", "lens_type": "CLEAR", "coating": "N",
                          "line": "economic", "index": "1.60"}, rx)
        self.assertEqual(r.status_code, 400)

    def test_readers_and_non_rx(self):
        r = self._create({"category": "READERS", "power": "2.25", "coating": "BLUE"})
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.data["sub_total"], "39.95")                 # 20 + 19.95
        self.assertEqual(r.data["reader_strength"], "+2.25")
        self.assertFalse(r.data["is_prescription_required"])
        r = self._create({"category": "NON_RX", "lens_type": "SUN", "tint": "POLARIZED", "color": "night-vision-yellow",
                          "coating": "N", "line": "economic", "index": "1.56"})
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.data["sub_total"], "59.95")                 # 20 + 39.95 (Free Upgrade, Q9)

    def test_progressive_add_checked_at_cart(self):
        sel = {"category": "PROGRESSIVE", "lens_type": "CLEAR", "coating": "N", "line": "economic", "index": "1.50"}
        r = self._create(sel, self._rx(sphere_r=-1, sphere_l=-1, add_r=4.0, add_l=4.0))
        self.assertEqual(r.status_code, 400)
        self.assertIn("ADD must be between", str(r.content))
        r = self._create(sel, self._rx(sphere_r=-1, sphere_l=-1, add_r=2.0, add_l=2.0))
        self.assertEqual(r.status_code, 201, r.content)

    def test_invalid_selection_rejected(self):
        r = self._create({"category": "SINGLE_VISION", "lens_type": "SUN", "tint": "SOLID", "color": "gray",
                          "line": "economic", "index": "1.56"}, self._rx())
        self.assertEqual(r.status_code, 400)
        self.assertIn("depth is required", str(r.content))

    def test_legacy_cart_items_unchanged(self):
        r = self.c.post("/api/order/createcompleteset", {"frame": {"sku": self.frame.sku}}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.data["sub_total"], "20.00")
        self.assertIsNone(r.data["lens_selection"])
