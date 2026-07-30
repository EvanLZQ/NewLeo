"""
Import lens_workflow reference data from Lens_Selection_Reference_Guide.xlsx.

Source of truth: lens_workflow/data/Lens_Selection_Reference_Guide.xlsx
(sheets: "Lens Types & Functions", "Index & Prices", "Color Compatibility",
"Coating").

Index recommendation brackets (LensIndexRecommendationRule) come from a
separate file, 镜片折射率推荐规则.xlsx, which is small (10 rows) and stable
enough to hardcode here rather than bundling a second xlsx — see
_import_index_recommendation_rules() for the exact mapping/notes.

Safe to re-run: everything goes through update_or_create. Blue Light
Blocking was retired as a Function (it's now a Coating, "Blue Light
Filtering") — any stale rows from a previous import are cleaned up.
"""
import os
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from lens_workflow.models import (
    LensType,
    LensFunctionPath,
    LensIndexOption,
    LensColorOption,
    LensCoating,
    LensIndexRecommendationRule,
)

DEFAULT_XLSX_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "data",
    "Lens_Selection_Reference_Guide.xlsx",
)

LENS_TYPE_CODES = {
    "SINGLE VISION - DISTANCE": "SVD",
    "SINGLE VISION - READING": "SVR",
    "BIFOCAL - WITH A LINE": "BIFOCAL",
    "PROGRESSIVE - NO LINE": "PROGRESSIVE",
    "NON-PRESCRIPTION": "NON_RX",
}

# Blue Light Blocking is no longer a Function — it's the "Blue Light
# Filtering" Coating option now (see COATING_CODES_BY_LABEL below).
FUNCTION_CODES = {
    "CLEAR": "CLEAR",
    "SUN": "SUN",
    "LIGHT ADJUSTING": "LIGHT_ADJUSTING",
}

SUN_TYPE_CODES = {
    "SOLID": "SOLID",
    "POLARIZED / MIRRORED": "POLARIZED_MIRRORED",
}

INDEX_RECOMMENDATION_CATEGORY_BY_LENS_TYPE = {
    "SVD": LensType.IndexRecommendationCategory.SINGLE_VISION,
    "SVR": LensType.IndexRecommendationCategory.SINGLE_VISION,
    "BIFOCAL": LensType.IndexRecommendationCategory.BIFOCAL_PROGRESSIVE,
    "PROGRESSIVE": LensType.IndexRecommendationCategory.BIFOCAL_PROGRESSIVE,
    "NON_RX": "",  # no prescription, no recommendation
}

COATING_CODES_BY_LABEL = {
    "No AR Coating": "NO_AR",
    "Standard AR Coating": "STANDARD_AR",
    "Premium AR Coating": "PREMIUM_AR",
    "Blue Light Filtering": "BLUE_LIGHT_FILTERING",
    "Hydrophobic": "HYDRO",
    "Oleophobic": "OLEO",
}


def _sun_type_code(raw):
    if not raw:
        return ""
    return SUN_TYPE_CODES[str(raw).strip()]


def _yes_no(raw):
    return str(raw).strip().lower() == "yes"


def _clean_option_label(raw_label, tier, index_value):
    """Some reference-guide rows are missing their label (data entry gap) —
    backfill using the same naming pattern as their sibling tiers."""
    label = str(raw_label or "").strip()
    if label:
        return label
    return f"{tier} Lenses - {index_value} Index"


def _rows_after_header(ws, header_first_cell):
    """Yield data rows (as tuples) after the row whose first cell matches header_first_cell."""
    rows = list(ws.iter_rows(values_only=True))
    header_idx = None
    for i, row in enumerate(rows):
        if row and row[0] == header_first_cell:
            header_idx = i
            break
    if header_idx is None:
        raise CommandError(
            f"Could not find header row starting with {header_first_cell!r} in sheet {ws.title!r}")
    for row in rows[header_idx + 1:]:
        if row and row[0] is not None:
            yield row


class Command(BaseCommand):
    help = "Import lens_workflow reference data (types/functions/index/color/coating/recommendations) from the reference xlsx."

    def add_arguments(self, parser):
        parser.add_argument(
            "--path",
            default=DEFAULT_XLSX_PATH,
            help="Path to Lens_Selection_Reference_Guide.xlsx (defaults to the copy checked into lens_workflow/data/).",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        try:
            import openpyxl
        except ImportError as e:
            raise CommandError(
                "openpyxl is required to run this command (pip install openpyxl).") from e

        path = options["path"]
        if not os.path.exists(path):
            raise CommandError(f"Reference guide not found at {path}")

        wb = openpyxl.load_workbook(path, data_only=True)

        self.stdout.write("Importing Lens Types & Functions...")
        lens_types, function_paths = self._import_lens_types_and_functions(
            wb["Lens Types & Functions"])

        self.stdout.write("Retiring stale Blue Light Blocking rows...")
        removed = LensFunctionPath.objects.filter(
            function_code="BLUE_LIGHT_BLOCKING").delete()[0]
        if removed:
            self.stdout.write(f"  removed {removed} stale row(s).")

        self.stdout.write("Importing Index & Prices...")
        index_options = self._import_index_options(
            wb["Index & Prices"], function_paths)

        self.stdout.write("Importing Color Compatibility...")
        self._import_color_options(wb["Color Compatibility"], function_paths)

        self.stdout.write("Importing Coatings...")
        self._import_coatings(wb["Coating"])

        self.stdout.write("Importing Index Recommendation Rules...")
        self._import_index_recommendation_rules()

        self.stdout.write(self.style.SUCCESS(
            f"Done: {len(lens_types)} lens types, {len(function_paths)} function paths, "
            f"{len(index_options)} index options."
        ))

    # ---------- Sheet 1: Lens Types & Functions ----------

    def _import_lens_types_and_functions(self, ws):
        lens_types = {}
        function_paths = {}

        for sort_idx, row in enumerate(_rows_after_header(ws, "Lens Type"), start=10):
            (lens_type_name, lens_type_desc, _step1_price,
             function_name, function_desc, _step2_price,
             sun_type_name, _step21_price, color_required, notes) = row

            lens_type_code = LENS_TYPE_CODES[lens_type_name.strip()]
            if lens_type_code not in lens_types:
                lens_types[lens_type_code] = LensType.objects.update_or_create(
                    code=lens_type_code,
                    defaults={
                        "label": lens_type_name.strip(),
                        "description": lens_type_desc or "",
                        "is_prescription_required": lens_type_code != "NON_RX",
                        "index_recommendation_category": INDEX_RECOMMENDATION_CATEGORY_BY_LENS_TYPE[lens_type_code],
                        "sort_order": len(lens_types) * 10 + 10,
                        "is_active": True,
                    },
                )[0]

            function_code = FUNCTION_CODES[function_name.strip()]
            sun_type_code = _sun_type_code(sun_type_name)

            fp, _ = LensFunctionPath.objects.update_or_create(
                lens_type=lens_types[lens_type_code],
                function_code=function_code,
                sun_type=sun_type_code,
                defaults={
                    "function_label": function_name.strip().title(),
                    "function_description": function_desc or "",
                    "color_required": _yes_no(color_required),
                    "extra_price": Decimal("0.00"),
                    "notes": notes or "",
                    "sort_order": sort_idx,
                    "is_active": True,
                },
            )
            function_paths[(lens_type_code, function_code, sun_type_code)] = fp

        return lens_types, function_paths

    # ---------- Sheet 2: Index & Prices ----------

    def _import_index_options(self, ws, function_paths):
        index_options = {}

        for sort_idx, row in enumerate(_rows_after_header(ws, "Lens Type"), start=10):
            (lens_type_name, function_name, sun_type_name, tier,
             option_label, index_value, price, _color_required, notes) = row

            key = (
                LENS_TYPE_CODES[lens_type_name.strip()],
                FUNCTION_CODES[function_name.strip()],
                _sun_type_code(sun_type_name),
            )
            function_path = function_paths.get(key)
            if function_path is None:
                raise CommandError(
                    f"Index & Prices row references unknown function path: {key} "
                    f"(option_label={option_label!r})"
                )

            clean_label = _clean_option_label(option_label, tier, index_value)

            index_option, _ = LensIndexOption.objects.update_or_create(
                function_path=function_path,
                option_label=clean_label,
                defaults={
                    "tier": tier or "",
                    "index_value": Decimal(str(index_value)),
                    "price": Decimal(str(price)),
                    "notes": notes or "",
                    "sort_order": sort_idx,
                    "is_active": True,
                },
            )
            index_options[(key, clean_label)] = index_option

        return index_options

    # ---------- Sheet 3: Color Compatibility ----------

    def _import_color_options(self, ws, function_paths):
        """
        A color's extra price doesn't vary by index tier, so this sheet's
        126 rows (one per index tier per color) collapse onto far fewer
        (function_path, color_name) combinations. If a color's price
        actually differs across tiers in the source data, that's a real
        inconsistency worth surfacing rather than silently picking whichever
        row happened to be processed last.

        Availability *does* vary by index tier (e.g. SVD's Polarized Green
        drops off at 1.67), so — unlike price — every index_value a color
        appears under is collected rather than collapsed, and written to
        available_index_values.
        """
        seen = {}  # (key, clean_color) -> {"price": Decimal, "function_path": obj, "indices": set}
        order = []
        for row in _rows_after_header(ws, "Lens Type"):
            (lens_type_name, function_name, sun_type_name,
             _option_label, index_value, color_name, extra_price) = row

            key = (
                LENS_TYPE_CODES[lens_type_name.strip()],
                FUNCTION_CODES[function_name.strip()],
                _sun_type_code(sun_type_name),
            )
            function_path = function_paths.get(key)
            if function_path is None:
                raise CommandError(
                    f"Color Compatibility row references unknown function path: "
                    f"{key} / color={color_name!r}"
                )

            clean_color = color_name.strip()
            price = Decimal(str(extra_price or 0))
            index_str = str(index_value).strip()

            entry_key = (key, clean_color)
            if entry_key not in seen:
                seen[entry_key] = {
                    "price": price,
                    "function_path": function_path,
                    "indices": set(),
                }
                order.append(entry_key)
            elif seen[entry_key]["price"] != price:
                raise CommandError(
                    f"Color {clean_color!r} under {key} has inconsistent extra_price "
                    f"across index tiers ({seen[entry_key]['price']} vs {price}) — "
                    "check the Color Compatibility sheet."
                )
            seen[entry_key]["indices"].add(index_str)

        count = 0
        for sort_idx, entry_key in enumerate(order, start=1):
            _, clean_color = entry_key
            data = seen[entry_key]
            _, created = LensColorOption.objects.update_or_create(
                function_path=data["function_path"],
                color_name=clean_color,
                defaults={
                    "extra_price": data["price"],
                    "available_index_values": sorted(data["indices"]),
                    "sort_order": sort_idx * 10,
                    "is_active": True,
                },
            )
            if created:
                count += 1
        return count

    # ---------- Sheet 4: Coating ----------

    def _import_coatings(self, ws):
        for sort_idx, row in enumerate(_rows_after_header(ws, "Coating Option"), start=10):
            label, description, recommended, price = row
            label = str(label).strip()
            code = COATING_CODES_BY_LABEL.get(label)
            if code is None:
                # Sheet has a trailing footer note ("All lenses come with
                # free scratch-resistant coating.") after the real rows —
                # not a coating option, skip it.
                continue
            LensCoating.objects.update_or_create(
                code=code,
                defaults={
                    "label": label,
                    "description": description or "",
                    "price": Decimal(str(price or 0)),
                    "is_recommended": _yes_no(recommended),
                    "sort_order": sort_idx,
                    "is_active": True,
                },
            )

    # ---------- Index recommendation rules (hardcoded — see module docstring) ----------

    def _import_index_recommendation_rules(self):
        # (max_combined_power, available_index_values, recommended_index_value)
        # None max = no upper bound (last/highest bracket).
        # Source sheet's "1.60" / "1.71" collapse into the real product
        # values "1.61" / "1.74" (confirmed with business owner — the
        # supplier only ever ships 1.61/1.74, never 1.60/1.71).
        SINGLE_VISION_BRACKETS = [
            (Decimal("3.00"), ["1.56", "1.61"], "1.56"),
            (Decimal("5.00"), ["1.56", "1.61"], "1.61"),
            (Decimal("6.00"), ["1.61", "1.67"], "1.67"),
            (Decimal("8.00"), ["1.67", "1.74"], "1.67"),
            (None, ["1.67", "1.74"], "1.74"),
        ]
        BIFOCAL_PROGRESSIVE_BRACKETS = [
            (Decimal("3.00"), ["1.50", "1.56"], "1.56"),
            (Decimal("5.00"), ["1.56", "1.61"], "1.61"),
            (Decimal("6.00"), ["1.61", "1.67"], "1.67"),
            (Decimal("8.00"), ["1.67", "1.74"], "1.67"),
            (None, ["1.74"], "1.74"),
        ]

        for category, brackets in [
            (LensIndexRecommendationRule.Category.SINGLE_VISION, SINGLE_VISION_BRACKETS),
            (LensIndexRecommendationRule.Category.BIFOCAL_PROGRESSIVE, BIFOCAL_PROGRESSIVE_BRACKETS),
        ]:
            for sort_idx, (max_power, available, recommended) in enumerate(brackets, start=10):
                LensIndexRecommendationRule.objects.update_or_create(
                    category=category,
                    sort_order=sort_idx,
                    defaults={
                        "max_combined_power": max_power,
                        "available_index_values": available,
                        "recommended_index_value": recommended,
                    },
                )
