"""
Seed lens_workflow reference data for the Shopping Flow Rebuild.

Unlike the retired import_lens_reference_guide command (which read a real
xlsx), this data has no clean spreadsheet source — it's transcribed by hand
from two places, both provided by the business owner:
  - "Eyelovewear Shopping Steps.xmind" (v2, priced) — the flow chart, and
    the only source that actually covers every Lens Type.
  - "Eyelovewear Pricing.xlsx" — called the pricing baseline, but only
    covers Single Vision Distance and disagrees with the mind map on a few
    SVD-specific numbers (Photochromic, Sun Gradient/Mirrored/Polarized).

Per the design principle established in the "Shopping Flow Rebuild" plan:
every price and every index/tint/coating tier is Django-admin-editable —
this seed is a reasonable starting point, not a locked-in decision. Safe to
re-run: everything goes through update_or_create.

Known assumptions worth a business review (not mechanical/low-stakes):
  1. Sun tint COLOR NAMES (e.g. "Polarized Green", "Gradient Brown") aren't
     given anywhere in the mind map or pricing xlsx — neither source
     enumerates specific colors per tint the way Photochromic's colors are
     spelled out. Reused the color names from this project's very first
     xlsx-based rebuild, remapped onto the new 4-tint structure (that
     source's "Solid" bucket split into today's Solid/Gradient, its
     "Polarized/Mirrored" bucket split into today's Polarized/Mirrored).
  2. Index recommendation brackets are hand-derived from the "折射率算法"
     sheet's descriptive, overlapping power ranges (with worked examples
     and astigmatism caveats) into the clean non-overlapping cutoffs this
     app's bracket model expects. Single Vision now has a real,
     direction-specific farsighted bracket set from the same sheet (see
     FARSIGHTED_SINGLE_VISION_BRACKETS below — confirmed with the business
     owner, no longer a guess). Bifocal/Progressive still has no
     farsighted-specific source data anywhere, so it keeps reusing its one
     bracket table for both signs (LensIndexRecommendationRule.direction="").
  3. Index 1.59 (the new polycarbonate safety lens) is included in the same
     availability bracket as 1.60/1.61 but never set as the *recommended*
     value — it reads as a lifestyle/safety choice (impact resistance for
     kids/sports) rather than a purely power-driven pick, so the algorithm
     doesn't default to it, but it's still selectable via "choose a
     different index."
  4. Reader Strength and the Reader Index both default to Free — no price
     was given for either in any source.

Eyelovewear Pricing(1).xlsx (v2, confirmed with the business owner — see
the "镜片购买流程改造方案" plan doc for the full comparison):
  - Every price already in this file matched the v2 sheet exactly except
    two brand-new SVD-only index tiers (see INDEX_TIERS_SVD): "1.61
    Driving" (same $19.95 as plain 1.61 — a distinct product/coating at
    the same refractive index, not a price change) and "1.71" ($59.95,
    between 1.67 and 1.74). Both SVD-only — the sheet's Reading and
    Progressive tables don't list either row.
  - v2 also drops Polarized from Reading's Sun tints entirely (every
    index row reads N/A) — TINT_PRICING["READING"] reflects that; see
    _seed_function_paths for how a None tint price deactivates any
    existing row instead of just skipping it.
  - v2's "EBD" column (a second price next to almost every Function/Tint
    cell) is a competitor's reference pricing, not Eyelovewear's own — not
    modeled here at all, confirmed not needed.
"""
from decimal import Decimal

from django.core.management.base import BaseCommand

from lens_workflow.models import (
    LensType,
    LensFunctionPath,
    LensIndexOption,
    LensColorOption,
    LensCoating,
    LensIndexRecommendationRule,
    LensReaderStrength,
)

D = Decimal

# ─────────────────────────────────────────────────────────────────────────
# Lens Types
# ─────────────────────────────────────────────────────────────────────────
LENS_TYPES = [
    # code, label, description, is_prescription_required, is_reader, index_recommendation_category
    ("SVD", "Single Vision Distance",
     "Single-vision distance lenses have one power all over the lens. They are made "
     "for seeing things far away, like driving and TV. They are not for reading up close.",
     True, False, LensType.IndexRecommendationCategory.SINGLE_VISION),
    ("READING", "Reading",
     "Reading eyeglasses are plus-power single-vision lenses. They help you focus on "
     "close-up things like books and phones, but they will blur your distance vision.",
     True, False, LensType.IndexRecommendationCategory.SINGLE_VISION),
    ("BIFOCAL", "Bifocals",
     "Bifocals have a visible line. Top part for distance, small bottom segment just "
     "for reading. They don't work well for computer screen distance.",
     True, False, LensType.IndexRecommendationCategory.BIFOCAL_PROGRESSIVE),
    ("PROGRESSIVE", "Progressives",
     "Progressives have no line. Power changes gradually: top for far, middle for "
     "computer, bottom for reading. Most people need a few days to get used to them.",
     True, False, LensType.IndexRecommendationCategory.BIFOCAL_PROGRESSIVE),
    ("NON_RX", "Non-prescription",
     "Non-prescription means these glasses are not made from your personal eye "
     "prescription. They can be zero-degree fashion glasses or over-the-counter "
     "reading glasses. They won't correct your specific vision needs.",
     False, False, ""),
    ("READER", "Reader",
     "Readymade reading glasses — pick a strength, no prescription needed.",
     False, True, ""),
]

# ─────────────────────────────────────────────────────────────────────────
# Function pricing per Lens Type. Sun's own price and each tint's price
# both apply — they stack (confirmed with the business owner). None for
# 'sun' means that Lens Type doesn't offer Sun at all (Bifocal, Reader).
# ─────────────────────────────────────────────────────────────────────────
FUNCTION_PRICING = {
    #                clear      blue_light  photochromic  sun
    "SVD":          (D("0"),    D("9.95"),  D("29.95"),   D("9.95")),
    "READING":      (D("0"),    D("9.95"),  D("29.95"),   D("9.95")),
    "NON_RX":       (D("0"),    D("9.95"),  D("29.95"),   D("9.95")),
    "PROGRESSIVE":  (D("39.95"), D("49.95"), D("89.95"),  D("49.95")),
    "BIFOCAL":      (D("29.95"), D("39.95"), D("79.95"),  None),
}

# Tint type pricing — Solid/Gradient/Mirrored/Polarized, per Lens Type.
# Only Lens Types offering Sun need an entry. A None price means that tint
# isn't offered for this Lens Type at all — e.g. Reading's Polarized,
# dropped in pricing sheet v2 (every index row reads N/A there).
TINT_PRICING = {
    #                solid      gradient    mirrored    polarized
    "SVD":          (D("9.95"),  D("12.95"), D("29.95"), D("39.95")),
    "READING":      (D("9.95"),  D("12.95"), D("29.95"), None),
    "NON_RX":       (D("9.95"),  D("12.95"), D("29.95"), D("39.95")),
    "PROGRESSIVE":  (D("0"),     D("9.95"),  D("29.95"), D("49.95")),
}

# ─────────────────────────────────────────────────────────────────────────
# Index / Material. Single Vision types get the full 6-tier ladder;
# Progressive/Bifocal deliberately only offer 4 (no 1.59 safety lens, no
# 1.74 ultra-thin — confirmed, not an omission).
# ─────────────────────────────────────────────────────────────────────────
INDEX_TIERS_FULL = [
    # index_value, price,     tier,        option_label
    ("1.50", D("4.95"),  "Basic",    "Basic - 1.50 Index"),
    ("1.56", D("6.95"),  "Standard", "Standard - 1.56 Index"),
    ("1.59", D("19.95"), "Safety",   "Safety - 1.59 Index (Polycarbonate)"),
    ("1.61", D("19.95"), "Popular",  "Popular - 1.61 Index"),
    ("1.67", D("39.95"), "Advanced", "Advanced - 1.67 Index"),
    ("1.74", D("79.95"), "Premium",  "Premium - 1.74 Index"),
]
INDEX_TIERS_NARROW = [row for row in INDEX_TIERS_FULL if row[0] in ("1.50", "1.56", "1.61", "1.67")]

# SVD-only, pricing sheet v2 — two extra tiers, confirmed not offered for
# any other Lens Type (Reading/Progressive's tables in the sheet don't list
# either row). "1.61 Driving" shares its index_value with plain "1.61
# Popular" on purpose — same refractive index, different product/coating —
# distinguished by tier, not by index_value (see LensIndexOption's
# uq_lens_index_option_type_value_tier constraint).
INDEX_TIERS_SVD = [
    ("1.50", D("4.95"),  "Basic",    "Basic - 1.50 Index"),
    ("1.56", D("6.95"),  "Standard", "Standard - 1.56 Index"),
    ("1.59", D("19.95"), "Safety",   "Safety - 1.59 Index (Polycarbonate)"),
    ("1.61", D("19.95"), "Popular",  "Popular - 1.61 Index"),
    ("1.61", D("19.95"), "Driving",  "Driving - 1.61 Index"),
    ("1.67", D("39.95"), "Advanced", "Advanced - 1.67 Index"),
    ("1.71", D("59.95"), "Elite",    "Elite - 1.71 Index"),
    ("1.74", D("79.95"), "Premium",  "Premium - 1.74 Index"),
]

INDEX_TIERS_BY_LENS_TYPE = {
    "SVD": INDEX_TIERS_SVD,
    "READING": INDEX_TIERS_FULL,
    "NON_RX": INDEX_TIERS_FULL,
    "PROGRESSIVE": INDEX_TIERS_NARROW,
    "BIFOCAL": INDEX_TIERS_NARROW,
}

# ─────────────────────────────────────────────────────────────────────────
# Colors
# ─────────────────────────────────────────────────────────────────────────
PHOTOCHROMIC_COLORS = {
    "SVD": ["Grey", "Brown"],
    "READING": ["Grey", "Brown"],
    "NON_RX": ["Grey", "Brown"],
    "PROGRESSIVE": ["Grey", "Brown", "Pink", "Purple", "Blue"],
    "BIFOCAL": ["Grey", "Brown"],
}

# Tint colors — same palette regardless of Lens Type (no source
# distinguishes them the way Photochromic's colors vary). Reused from this
# project's original xlsx-based rebuild, remapped onto the new tiers — see
# assumption #1 in the module docstring.
TINT_COLORS = {
    "SOLID":     ["50% Gray", "50% Brown", "50% Green", "50% Blue",
                  "80% Gray", "80% Brown", "80% Green", "80% Blue"],
    "GRADIENT":  ["Gradient Brown", "Gradient Green", "Gradient Gray",
                  "Gradient Purple", "Gradient Blue"],
    "MIRRORED":  ["Mirrored Silver", "Mirrored Blue"],
    "POLARIZED": ["Polarized Green", "Polarized Gray", "Polarized Brown"],
}

# ─────────────────────────────────────────────────────────────────────────
# Coatings — universal, not scoped to Lens Type.
# ─────────────────────────────────────────────────────────────────────────
COATINGS = [
    # code, label, price, is_included, exclusive_group, is_recommended
    ("ANTI_SCRATCH", "Anti-scratch",
     "A hard protective layer that helps prevent fine daily scratches. "
     "Scratch-resistant, not scratch-proof.", D("0"), True, "", False),
    ("ANTI_GLARE", "Anti-glare",
     "Cuts reflections from lights, screens, and night-time headlights for "
     "clearer vision, especially driving after dark.", D("0"), True, "", False),
    ("UV_PROTECTION", "UV Protection",
     "Blocks harmful UVA and UVB sunlight from reaching your eyes.", D("0"), True, "", False),
    # is_recommended reset False -> True previously had no visible effect
    # anywhere (the Coating step doesn't special-case it today) — now it
    # also controls whether this coating gets auto-added to the
    # Recommended Complete Lens bundle (lens_workflow/views.py
    # LensWorkflowRecommendView). Confirmed with the business owner: don't
    # proactively upsell a paid coating there at launch; flip this in the
    # admin later to change that, no code change needed.
    ("BLUE_LIGHT_FILTERING", "Blue Light Filtering",
     "Filters some of the blue light from phone and computer screens.",
     D("9.95"), False, "", False),
    ("OLEOPHOBIC", "Oleophobic",
     "Repels oil and fingerprints — smudges wipe off more easily.",
     D("4.95"), False, "OLEO_HYDRO", False),
    ("HYDROPHOBIC", "Hydrophobic",
     "Repels water, fingerprints, and oil — includes Oleophobic's benefit.",
     D("9.95"), False, "OLEO_HYDRO", False),
]

# ─────────────────────────────────────────────────────────────────────────
# Reader strengths — +0.25 to +3.00 in 0.25 steps, all 12 values (the
# diagram's list skipped +2.50 by mistake — confirmed, included here).
# ─────────────────────────────────────────────────────────────────────────
READER_STRENGTHS = [D(f"{n/100:.2f}") for n in range(25, 301, 25)]

# ─────────────────────────────────────────────────────────────────────────
# Index recommendation brackets — see assumptions #2/#3 above.
# ─────────────────────────────────────────────────────────────────────────
SINGLE_VISION_NEARSIGHTED_BRACKETS = [
    # max_combined_power, available_index_values, recommended
    (D("2.00"), ["1.50", "1.56"], "1.50"),
    (D("4.00"), ["1.50", "1.56", "1.59", "1.61"], "1.56"),
    (D("6.00"), ["1.56", "1.59", "1.61", "1.67"], "1.61"),
    (D("8.00"), ["1.61", "1.67", "1.74"], "1.67"),
    (None,      ["1.67", "1.74"], "1.74"),
]

# Farsighted-specific — the "折射率算法" sheet gives a separate, coarser
# table for farsighted prescriptions (max index it ever suggests is 1.67 —
# 1.59/1.71/1.74 never come up). Confirmed real data, not a guess.
SINGLE_VISION_FARSIGHTED_BRACKETS = [
    (D("2.00"), ["1.50", "1.56"], "1.50"),
    (D("4.00"), ["1.50", "1.56", "1.61"], "1.56"),
    (None,      ["1.56", "1.61", "1.67"], "1.67"),
]

# No farsighted-specific source data exists for Bifocal/Progressive
# anywhere — direction stays "" (applies to either sign) on these, unlike
# Single Vision above.
BIFOCAL_PROGRESSIVE_BRACKETS = [
    (D("3.00"), ["1.50", "1.56"], "1.50"),
    (D("5.00"), ["1.50", "1.56", "1.61"], "1.56"),
    (D("6.00"), ["1.56", "1.61"], "1.61"),
    (None,      ["1.61", "1.67"], "1.67"),
]


class Command(BaseCommand):
    help = "Seed lens_workflow reference data for the Shopping Flow Rebuild (see module docstring for sources)."

    def handle(self, *args, **options):
        lens_types = self._seed_lens_types()
        function_paths = self._seed_function_paths(lens_types)
        self._seed_index_options(lens_types)
        self._seed_colors(function_paths, lens_types)
        self._seed_coatings()
        self._seed_reader_strength()
        self._seed_recommendation_rules()
        self.stdout.write(self.style.SUCCESS(
            f"Done: {len(lens_types)} lens types, {len(function_paths)} function paths."
        ))

    # ---------- Lens Types ----------

    def _seed_lens_types(self):
        self.stdout.write("Seeding Lens Types...")
        lens_types = {}
        for sort_idx, (code, label, desc, needs_rx, is_reader, category) in enumerate(LENS_TYPES, start=10):
            lt, _ = LensType.objects.update_or_create(
                code=code,
                defaults={
                    "label": label,
                    "description": desc,
                    "is_prescription_required": needs_rx,
                    "is_reader": is_reader,
                    "index_recommendation_category": category,
                    "sort_order": sort_idx * 10,
                    "is_active": True,
                },
            )
            lens_types[code] = lt
        return lens_types

    # ---------- Function Paths (Classic / Blue-light / Photochromic / Sun + tints) ----------

    def _seed_function_paths(self, lens_types):
        self.stdout.write("Seeding Function Paths...")
        function_paths = {}
        for lt_code, (clear_p, blue_p, photo_p, sun_p) in FUNCTION_PRICING.items():
            lens_type = lens_types[lt_code]

            fp, _ = LensFunctionPath.objects.update_or_create(
                lens_type=lens_type, function_code=LensFunctionPath.FunctionCode.CLEAR, sun_type="",
                defaults=dict(function_label="Classic",
                              function_description="Clear lenses, completely transparent with no color. "
                                                    "UV-blocking with scratch-resistant, anti-reflective coatings.",
                              color_required=False, extra_price=clear_p, sort_order=10, is_active=True),
            )
            function_paths[(lt_code, "CLEAR", "")] = fp

            fp, _ = LensFunctionPath.objects.update_or_create(
                lens_type=lens_type, function_code=LensFunctionPath.FunctionCode.BLUE_LIGHT_FILTERING, sun_type="",
                defaults=dict(function_label="Blue Light Filtering",
                              function_description="Blocks some of the blue light from phone and computer screens.",
                              color_required=False, extra_price=blue_p, sort_order=20, is_active=True),
            )
            function_paths[(lt_code, "BLUE_LIGHT_FILTERING", "")] = fp

            fp, _ = LensFunctionPath.objects.update_or_create(
                lens_type=lens_type, function_code=LensFunctionPath.FunctionCode.PHOTOCHROMIC, sun_type="",
                defaults=dict(function_label="Light-responsive / Photochromic",
                              function_description="Turns clear indoors and darkens in sunlight like sunglasses.",
                              color_required=True, extra_price=photo_p, sort_order=30, is_active=True),
            )
            function_paths[(lt_code, "PHOTOCHROMIC", "")] = fp

            if sun_p is None:
                continue  # Bifocal — no Sun at all

            fp, _ = LensFunctionPath.objects.update_or_create(
                lens_type=lens_type, function_code=LensFunctionPath.FunctionCode.SUN, sun_type="",
                defaults=dict(function_label="Sun",
                              function_description="Tinted sun lenses with a fixed color — "
                                                    "block 100% of UVA and UVB rays.",
                              color_required=False, extra_price=sun_p, sort_order=40, is_active=True),
            )
            function_paths[(lt_code, "SUN", "")] = fp

            tint_prices = TINT_PRICING[lt_code]
            tint_defs = [
                (LensFunctionPath.SunType.SOLID, "Solid", tint_prices[0],
                 "Stylish sun tints in a range of colors with UV protection."),
                (LensFunctionPath.SunType.GRADIENT, "Gradient", tint_prices[1],
                 "Darker at the top, lighter toward the bottom — blocks overhead sun while "
                 "keeping your phone or menu readable."),
                (LensFunctionPath.SunType.MIRRORED, "Mirrored", tint_prices[2],
                 "A shiny metallic reflective coating for the popular mirror-sunglass look."),
                (LensFunctionPath.SunType.POLARIZED, "Polarized", tint_prices[3],
                 "Blocks harsh reflected glare from roads and water."),
            ]
            for sort_idx, (tint_code, tint_label, price, desc) in enumerate(tint_defs, start=41):
                lookup = dict(lens_type=lens_type, function_code=LensFunctionPath.FunctionCode.SUN,
                              sun_type=tint_code)
                if price is None:
                    # Not offered for this Lens Type (e.g. Reading + Polarized,
                    # dropped in pricing sheet v2) — deactivate any row a prior
                    # seed run left behind instead of silently leaving it live.
                    LensFunctionPath.objects.filter(**lookup).update(is_active=False)
                    continue

                fp, _ = LensFunctionPath.objects.update_or_create(
                    **lookup,
                    defaults=dict(function_label=tint_label, function_description=desc,
                                  color_required=True, extra_price=price, sort_order=sort_idx, is_active=True),
                )
                function_paths[(lt_code, "SUN", tint_code)] = fp

        return function_paths

    # ---------- Index / Material ----------

    def _seed_index_options(self, lens_types):
        self.stdout.write("Seeding Index Options...")
        for lt_code, tiers in INDEX_TIERS_BY_LENS_TYPE.items():
            lens_type = lens_types[lt_code]
            for sort_idx, (index_value, price, tier, label) in enumerate(tiers, start=10):
                # tier is part of the lookup key (not just a default) — see
                # INDEX_TIERS_SVD's "1.61 Driving" sharing index_value with
                # "1.61 Popular"; without tier here the second row would
                # overwrite the first instead of creating a sibling.
                LensIndexOption.objects.update_or_create(
                    lens_type=lens_type, index_value=Decimal(index_value), tier=tier,
                    defaults=dict(option_label=label, price=price,
                                  sort_order=sort_idx * 10, is_active=True),
                )

        # Reader gets exactly one fixed, free index — no interactive Material step.
        LensIndexOption.objects.update_or_create(
            lens_type=lens_types["READER"], index_value=Decimal("1.50"), tier="Reader",
            defaults=dict(option_label="Reader Index", price=D("0"),
                          sort_order=10, is_active=True),
        )

    # ---------- Colors ----------

    def _seed_colors(self, function_paths, lens_types):
        self.stdout.write("Seeding Colors...")
        for lt_code, colors in PHOTOCHROMIC_COLORS.items():
            fp = function_paths[(lt_code, "PHOTOCHROMIC", "")]
            available = self._index_values_for(lens_types[lt_code])
            for sort_idx, color_name in enumerate(colors, start=1):
                LensColorOption.objects.update_or_create(
                    function_path=fp, color_name=color_name,
                    defaults=dict(extra_price=D("0"), available_index_values=available,
                                  sort_order=sort_idx * 10, is_active=True),
                )

        for lt_code in TINT_PRICING:
            available = self._index_values_for(lens_types[lt_code])
            for tint_code, colors in TINT_COLORS.items():
                fp = function_paths.get((lt_code, "SUN", tint_code))
                if fp is None:
                    continue
                for sort_idx, color_name in enumerate(colors, start=1):
                    LensColorOption.objects.update_or_create(
                        function_path=fp, color_name=color_name,
                        defaults=dict(extra_price=D("0"), available_index_values=available,
                                      sort_order=sort_idx * 10, is_active=True),
                    )

    def _index_values_for(self, lens_type):
        """All active index_value strings for this Lens Type — used as
        available_index_values on colors that have no narrower, specific
        restriction. NOT an empty list — an empty list would mean
        'available at zero index values' to the workflow API, the
        opposite of what's intended here."""
        # dict.fromkeys dedupes while keeping order — SVD now has two rows
        # sharing index_value "1.61" (Popular/Driving), which would
        # otherwise appear twice in this list for no reason.
        return list(dict.fromkeys(
            str(v) for v in
            LensIndexOption.objects.filter(lens_type=lens_type, is_active=True)
            .values_list("index_value", flat=True)
        )) or [row[0] for row in INDEX_TIERS_BY_LENS_TYPE.get(lens_type.code, [])]

    # ---------- Coatings ----------

    def _seed_coatings(self):
        self.stdout.write("Seeding Coatings...")
        for sort_idx, (code, label, desc, price, is_included, group, is_recommended) in enumerate(COATINGS, start=10):
            LensCoating.objects.update_or_create(
                code=code,
                defaults=dict(label=label, description=desc, price=price,
                              is_included=is_included, exclusive_group=group,
                              is_recommended=is_recommended, sort_order=sort_idx * 10, is_active=True),
            )

    # ---------- Reader Strength ----------

    def _seed_reader_strength(self):
        self.stdout.write("Seeding Reader Strengths...")
        for sort_idx, value in enumerate(READER_STRENGTHS, start=10):
            LensReaderStrength.objects.update_or_create(
                strength_value=value,
                defaults=dict(label=f"+{value}", price=D("0"),
                              sort_order=sort_idx * 10, is_active=True),
            )

    # ---------- Index Recommendation Rules ----------

    def _seed_recommendation_rules(self):
        self.stdout.write("Seeding Index Recommendation Rules...")
        Direction = LensIndexRecommendationRule.Direction

        # Pre-migration, every Single Vision rule had direction="" (the
        # field didn't exist). Now that Single Vision has real
        # direction-specific data, those blank rows are dead — nothing
        # matches them any more (see _match_recommendation_rule: a
        # direction-specific query always finds rows below for this
        # category, so it never falls through to blank ones). Clear them
        # instead of leaving unreachable rows sitting in the admin.
        LensIndexRecommendationRule.objects.filter(
            category=LensIndexRecommendationRule.Category.SINGLE_VISION, direction="",
        ).delete()

        for category, direction, brackets in [
            (LensIndexRecommendationRule.Category.SINGLE_VISION, Direction.NEARSIGHTED,
             SINGLE_VISION_NEARSIGHTED_BRACKETS),
            (LensIndexRecommendationRule.Category.SINGLE_VISION, Direction.FARSIGHTED,
             SINGLE_VISION_FARSIGHTED_BRACKETS),
            (LensIndexRecommendationRule.Category.BIFOCAL_PROGRESSIVE, "",
             BIFOCAL_PROGRESSIVE_BRACKETS),
        ]:
            for sort_idx, (max_power, available, recommended) in enumerate(brackets, start=10):
                LensIndexRecommendationRule.objects.update_or_create(
                    category=category, direction=direction, sort_order=sort_idx,
                    defaults=dict(max_combined_power=max_power,
                                  available_index_values=available,
                                  recommended_index_value=recommended),
                )
