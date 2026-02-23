# management/commands/seed_lens_flow.py
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from lens_workflow.models import (  # <-- change "your_app" to your actual app name
    LensStep,
    LensOption,
    LensStepRule,
    LensOptionAvailability,
)


class Command(BaseCommand):
    help = "Seed initial lens workflow (steps, options, rules, availability)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete existing lens flow data before seeding.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        reset = options["reset"]

        if reset:
            self.stdout.write(self.style.WARNING(
                "Resetting lens flow tables..."))
            LensOptionAvailability.objects.all().delete()
            LensStepRule.objects.all().delete()
            LensOption.objects.all().delete()
            LensStep.objects.all().delete()

        self.stdout.write("Seeding lens steps...")
        steps = self._seed_steps()

        self.stdout.write("Seeding lens options...")
        opts = self._seed_options()

        self.stdout.write("Seeding step rules...")
        self._seed_step_rules(steps, opts)

        self.stdout.write("Seeding option availability...")
        self._seed_availability(opts)

        self.stdout.write(self.style.SUCCESS("Lens flow seed complete."))

    # ---------- Seed helpers ----------

    def _seed_steps(self):
        """
        Step order:
        1) Color Type
        2) Color (conditional)
        3) Index
        4) Coating
        """
        step_data = [
            ("COLOR_TYPE", "Lens Type", 10,
             "First step: user chooses clear/blue-light/sun/photochromic"),
            ("COLOR", "Lens Color", 20, "Shown for Sun/Tinted and Light Adjusting"),
            ("INDEX", "Lens Index", 30, "Choose index after color type or color"),
            ("COATING", "Lens Coating", 40, "Final step after index"),
        ]

        result = {}
        for code, label, sort_order, description in step_data:
            step, _ = LensStep.objects.update_or_create(
                code=code,
                defaults={
                    "label": label,
                    "description": description,
                    "sort_order": sort_order,
                    "is_active": True,
                },
            )
            result[code] = step
        return result

    def _seed_options(self):
        result = {}

        # --- COLOR_TYPE options ---
        color_types = [
            {
                "code": "CLEAR",
                "name": "Clear",
                "option_type": "COLOR_TYPE",
                "price": Decimal("0.00"),
                "sort_order": 10,
                "metadata": {"ui_group": "basic"},
            },
            {
                "code": "BLUE_LIGHT",
                "name": "Blue Light Filtering",
                "option_type": "COLOR_TYPE",
                "price": Decimal("20.00"),
                "sort_order": 20,
                "metadata": {"ui_group": "basic"},
            },
            {
                "code": "SUN_TINTED",
                "name": "Sun/Tinted",
                "option_type": "COLOR_TYPE",
                "price": Decimal("30.00"),
                "sort_order": 30,
                "metadata": {"ui_group": "sun"},
            },
            {
                "code": "LIGHT_ADJUSTING",
                "name": "Light Adjusting",
                "option_type": "COLOR_TYPE",
                "price": Decimal("80.00"),
                "sort_order": 40,
                "metadata": {"ui_group": "photochromic"},
            },
        ]

        # --- COLOR options (for Sun/Tinted and Light Adjusting) ---
        colors = [
            {
                "code": "SUN_SOLID_GRAY_50",
                "name": "Solid Gray 50%",
                "option_type": "COLOR",
                "price": Decimal("0.00"),
                "sort_order": 10,
                "metadata": {
                    "family": "solid",
                    "base_color": "gray",
                    "density": "50",
                    "swatch_hex": "#6b7280",
                },
            },
            {
                "code": "SUN_SOLID_BROWN_80",
                "name": "Solid Brown 80%",
                "option_type": "COLOR",
                "price": Decimal("0.00"),
                "sort_order": 20,
                "metadata": {
                    "family": "solid",
                    "base_color": "brown",
                    "density": "80",
                    "swatch_hex": "#7c4a2d",
                },
            },
            {
                "code": "SUN_SOLID_GREEN_80",
                "name": "Solid Green 80%",
                "option_type": "COLOR",
                "price": Decimal("0.00"),
                "sort_order": 30,
                "metadata": {
                    "family": "solid",
                    "base_color": "green",
                    "density": "80",
                    "swatch_hex": "#3f5b45",
                },
            },
            {
                "code": "SUN_MIRROR_BLUE",
                "name": "Mirrored Blue",
                "option_type": "COLOR",
                "price": Decimal("15.00"),
                "sort_order": 40,
                "metadata": {
                    "family": "mirrored",
                    "base_color": "blue",
                    "swatch_hex": "#4f86c6",
                },
            },
            {
                "code": "SUN_POLARIZED_G15",
                "name": "Polarized G15 Green",
                "option_type": "COLOR",
                "price": Decimal("35.00"),
                "sort_order": 50,
                "metadata": {
                    "family": "polarized",
                    "base_color": "green",
                    "swatch_hex": "#556b5d",
                },
            },
            {
                "code": "PHOTO_GRAY",
                "name": "Photochromic Gray",
                "option_type": "COLOR",
                "price": Decimal("0.00"),
                "sort_order": 60,
                "metadata": {
                    "family": "photochromic",
                    "base_color": "gray",
                    "swatch_hex": "#6b7280",
                },
            },
            {
                "code": "PHOTO_BROWN",
                "name": "Photochromic Brown",
                "option_type": "COLOR",
                "price": Decimal("0.00"),
                "sort_order": 70,
                "metadata": {
                    "family": "photochromic",
                    "base_color": "brown",
                    "swatch_hex": "#7c4a2d",
                },
            },
        ]

        # --- INDEX options ---
        indexes = [
            {
                "code": "INDEX_156",
                "name": "Standard (1.56)",
                "option_type": "INDEX",
                "price": Decimal("0.00"),
                "sort_order": 10,
                "metadata": {"index_value": "1.56"},
            },
            {
                "code": "INDEX_160",
                "name": "Mid-Index (1.60)",
                "option_type": "INDEX",
                "price": Decimal("35.00"),
                "sort_order": 20,
                "metadata": {"index_value": "1.60"},
            },
            {
                "code": "INDEX_167",
                "name": "High-Index (1.67)",
                "option_type": "INDEX",
                "price": Decimal("75.00"),
                "sort_order": 30,
                "metadata": {"index_value": "1.67"},
            },
        ]

        # --- COATING options ---
        coatings = [
            {
                "code": "COAT_STANDARD_AR",
                "name": "Standard AR Coating",
                "option_type": "COATING",
                "price": Decimal("0.00"),
                "sort_order": 10,
                "metadata": {"category": "ar"},
            },
            {
                "code": "COAT_PREMIUM_AR",
                "name": "Premium AR Coating",
                "option_type": "COATING",
                "price": Decimal("25.00"),
                "sort_order": 20,
                "metadata": {"category": "ar"},
            },
            {
                "code": "COAT_HYDRO",
                "name": "Hydrophobic",
                "option_type": "COATING",
                "price": Decimal("15.00"),
                "sort_order": 30,
                "metadata": {"category": "performance"},
            },
            {
                "code": "COAT_OLEO",
                "name": "Oleophobic",
                "option_type": "COATING",
                "price": Decimal("15.00"),
                "sort_order": 40,
                "metadata": {"category": "performance"},
            },
        ]

        all_options = color_types + colors + indexes + coatings

        for item in all_options:
            obj, _ = LensOption.objects.update_or_create(
                code=item["code"],
                defaults={
                    "name": item["name"],
                    "option_type": item["option_type"],
                    "description": item.get("description", ""),
                    "add_on_price": item["price"],
                    "image_url": item.get("image_url", ""),
                    "metadata": item.get("metadata", {}),
                    "sort_order": item["sort_order"],
                    "is_active": True,
                },
            )
            result[item["code"]] = obj

        return result

    def _seed_step_rules(self, steps, opts):
        """
        Flow rules:
        COLOR_TYPE:
          CLEAR -> INDEX
          BLUE_LIGHT -> INDEX
          SUN_TINTED -> COLOR
          LIGHT_ADJUSTING -> COLOR

        COLOR:
          any COLOR option -> INDEX

        INDEX:
          any INDEX option -> COATING
        """
        # Clear existing rules for the seeded step/option combos (idempotent seed)
        # We use update_or_create below, so no hard delete necessary.

        # COLOR_TYPE rules
        self._upsert_rule(steps["COLOR_TYPE"],
                          opts["CLEAR"], steps["INDEX"], priority=10)
        self._upsert_rule(steps["COLOR_TYPE"],
                          opts["BLUE_LIGHT"], steps["INDEX"], priority=20)
        self._upsert_rule(steps["COLOR_TYPE"],
                          opts["SUN_TINTED"], steps["COLOR"], priority=30)
        self._upsert_rule(
            steps["COLOR_TYPE"], opts["LIGHT_ADJUSTING"], steps["COLOR"], priority=40)

        # COLOR -> INDEX (for all COLOR options)
        color_options = LensOption.objects.filter(
            option_type="COLOR", is_active=True)
        for i, color_opt in enumerate(color_options, start=10):
            self._upsert_rule(steps["COLOR"], color_opt,
                              steps["INDEX"], priority=i)

        # INDEX -> COATING (for all INDEX options)
        index_options = LensOption.objects.filter(
            option_type="INDEX", is_active=True)
        for i, index_opt in enumerate(index_options, start=10):
            self._upsert_rule(steps["INDEX"], index_opt,
                              steps["COATING"], priority=i)

    def _seed_availability(self, opts):
        """
        Defines what child options appear after a parent option is selected.

        1) COLOR_TYPE -> INDEX (for CLEAR / BLUE_LIGHT)
        2) COLOR_TYPE -> COLOR (for SUN_TINTED / LIGHT_ADJUSTING)
        3) COLOR -> INDEX
        4) INDEX -> COATING
        """

        # Helper lists
        index_codes_clear_blue = ["INDEX_156", "INDEX_160", "INDEX_167"]
        index_codes_sun = ["INDEX_156", "INDEX_160", "INDEX_167"]
        # Example restriction: photochromic excludes 1.67
        index_codes_photo = ["INDEX_156", "INDEX_160"]
        coating_codes_all = ["COAT_STANDARD_AR",
                             "COAT_PREMIUM_AR", "COAT_HYDRO", "COAT_OLEO"]

        sun_color_codes = [
            "SUN_SOLID_GRAY_50",
            "SUN_SOLID_BROWN_80",
            "SUN_SOLID_GREEN_80",
            "SUN_MIRROR_BLUE",
            "SUN_POLARIZED_G15",
        ]
        photo_color_codes = [
            "PHOTO_GRAY",
            "PHOTO_BROWN",
        ]

        # 1) CLEAR / BLUE_LIGHT -> INDEX
        for sort_idx, code in enumerate(index_codes_clear_blue, start=10):
            self._upsert_availability(
                opts["CLEAR"], opts[code], sort_order=sort_idx)
            self._upsert_availability(
                opts["BLUE_LIGHT"], opts[code], sort_order=sort_idx)

        # 2) SUN_TINTED -> available COLORs
        for sort_idx, code in enumerate(sun_color_codes, start=10):
            self._upsert_availability(
                opts["SUN_TINTED"], opts[code], sort_order=sort_idx)

        # 2b) LIGHT_ADJUSTING -> available COLORs (photochromic colors only)
        for sort_idx, code in enumerate(photo_color_codes, start=10):
            self._upsert_availability(
                opts["LIGHT_ADJUSTING"], opts[code], sort_order=sort_idx)

        # 3) COLOR -> INDEX
        # Sun/Tinted colors get all 3 indexes
        for color_code in sun_color_codes:
            for sort_idx, idx_code in enumerate(index_codes_sun, start=10):
                self._upsert_availability(
                    opts[color_code], opts[idx_code], sort_order=sort_idx)

        # Light-adjusting/photochromic colors get restricted indexes
        for color_code in photo_color_codes:
            for sort_idx, idx_code in enumerate(index_codes_photo, start=10):
                self._upsert_availability(
                    opts[color_code], opts[idx_code], sort_order=sort_idx)

        # 4) INDEX -> COATING
        # Example restrictions:
        # - 1.56 gets all coatings
        # - 1.60 gets all coatings
        # - 1.67 gets premium + hydro + oleo (skip standard AR)
        for sort_idx, coat_code in enumerate(coating_codes_all, start=10):
            self._upsert_availability(
                opts["INDEX_156"], opts[coat_code], sort_order=sort_idx)
            self._upsert_availability(
                opts["INDEX_160"], opts[coat_code], sort_order=sort_idx)

        index_167_coats = ["COAT_PREMIUM_AR", "COAT_HYDRO", "COAT_OLEO"]
        for sort_idx, coat_code in enumerate(index_167_coats, start=10):
            self._upsert_availability(
                opts["INDEX_167"], opts[coat_code], sort_order=sort_idx)

    # ---------- Upsert helpers ----------

    def _upsert_rule(self, current_step, selected_option, next_step, priority=0):
        LensStepRule.objects.update_or_create(
            current_step=current_step,
            selected_option=selected_option,
            defaults={
                "next_step": next_step,
                "priority": priority,
                "is_active": True,
                "notes": "",
            },
        )

    def _upsert_availability(self, parent_option, child_option, sort_order=0):
        LensOptionAvailability.objects.update_or_create(
            parent_option=parent_option,
            child_option=child_option,
            defaults={
                "sort_order": sort_order,
                "is_active": True,
                "notes": "",
            },
        )
