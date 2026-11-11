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
  2. Index recommendation is the absolute steep meridian (the larger of
     |S| and |S+C|, stronger eye wins), not spherical equivalent and not
     the price sheet's Recommended SE column. The brackets are the same
     for every lens category and both signs: 0.00–±2.00 → 1.50,
     ±2.25–±4.00 → 1.60/1.61, ±4.25–±6.00 → 1.67, ±6.25 and above → 1.74.
     The rows written below mirror that table for the admin. The shopping
     flow reads the code table, not these rows.
  3. Driving 1.61, Safety 1.59 (polycarbonate), and Elite 1.71 are not on
     the price sheet. They are not seeded, and any row a previous seed
     left behind is set inactive (orders may still point at it).
  4. Reader Strength and the Reader Index both default to Free — no price
     was given for either in any source.

Eyelovewear Pricing(1).xlsx (v2, confirmed with the business owner — see
the "镜片购买流程改造方案" plan doc for the full comparison):
  - v2 drops Polarized from Reading's Sun tints entirely (every index row
    reads N/A) — TINT_PRICING["READING"] reflects that; see
    _seed_function_paths for how a None tint price deactivates any
    existing row instead of just skipping it.
  - v2's "EBD" column (a second price next to almost every Function/Tint
    cell) is a competitor's reference pricing, not Eyelovewear's own — not
    modeled here at all, confirmed not needed.
  - Driving 1.61, Safety 1.59, and Elite 1.71 were seeded from an earlier
    sheet and are not on the current price file. Re-running this command
    does not recreate them as active options.
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
from lens_workflow.pricing import STEEP_MERIDIAN_BRACKETS, available_index_labels

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
# Index / Material. The ladder is 1.50, 1.56, 1.61 (sheet 1.60), 1.67, 1.74.
# Driving 1.61, Safety 1.59, and Elite 1.71 are not on the price sheet and
# are not seeded. Progressive and Bifocal include 1.74, which the premium
# sheet does price.
# ─────────────────────────────────────────────────────────────────────────
INDEX_TIERS_FULL = [
    # index_value, price,     tier,        option_label
    ("1.50", D("4.95"),  "Basic",    "Basic - 1.50 Index"),
    ("1.56", D("6.95"),  "Standard", "Standard - 1.56 Index"),
    ("1.61", D("19.95"), "Popular",  "Popular - 1.61 Index"),
    ("1.67", D("39.95"), "Advanced", "Advanced - 1.67 Index"),
    ("1.74", D("79.95"), "Premium",  "Premium - 1.74 Index"),
]
# Progressive and Bifocal include 1.74 because the premium sheet has cells
# for it. The number here is the catalog add-on, the same one SVD uses.
# The sheet cell is still the price at checkout.
INDEX_TIERS_NARROW = [row for row in INDEX_TIERS_FULL if row[0] in ("1.50", "1.56", "1.61", "1.67", "1.74")]
# Kept as its own list so an SVD-only tier can be added without coming back
# through INDEX_TIERS_FULL. It matches FULL now that Driving / Safety / Elite
# are gone.
INDEX_TIERS_SVD = list(INDEX_TIERS_FULL)

# Name + index of catalog rows that must stay inactive if a previous seed
# created them. Matched in Python, not by primary key.
RETIRED_INDEX_OPTIONS = (
    (D("1.61"), ("driving",)),
    (D("1.59"), ("safety", "polycarbonate")),
    (D("1.71"), ("elite",)),
)

# Shopper-facing notes on the index step (LensIndexOption.notes). Material
# and Abbe are separate fields, so this copy does not repeat them and does
# not mention the price sheet or how a tier was chosen.
INDEX_RATIONALE = {
    "1.50": ("Our clearest lens. A good choice for mild prescriptions, where a "
             "thinner lens would not change how the glasses look."),
    "1.56": ("A little thinner than our clearest lens, for a small step up in price."),
    "1.61": ("Thinner and light, with clear vision for everyday wear."),
    "1.67": ("A thinner, lighter lens for stronger prescriptions."),
    "1.74": ("Our thinnest lens, for strong prescriptions. It looks best in a full frame."),
}

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

# Swatch rendering per color_name — feeds LensColorOption.swatch_hex/
# swatch_density/swatch_family/base_color, which _color_option_dict passes
# through as option.metadata for the frontend's getSwatchStyle (see
# lensWorkFlow.d.ts's LensWorkflowOptionMetadata comment — this was the
# missing half of an already-built frontend swatch renderer).
# Keyed by the exact color_name string above, so "50% Gray" and "80% Gray"
# share the same base hex but different density — the whole point being
# that two densities of one hue render as visibly different dots without
# needing two different colors.
COLOR_SWATCH_INFO = {
    # SOLID — density parsed from the literal "NN%" prefix
    "50% Gray":  ("#808080", "0.50", LensColorOption.Family.SOLID, "Gray"),
    "50% Brown": ("#6B4226", "0.50", LensColorOption.Family.SOLID, "Brown"),
    "50% Green": ("#2E6B4F", "0.50", LensColorOption.Family.SOLID, "Green"),
    "50% Blue":  ("#3B5BA5", "0.50", LensColorOption.Family.SOLID, "Blue"),
    "80% Gray":  ("#808080", "0.80", LensColorOption.Family.SOLID, "Gray"),
    "80% Brown": ("#6B4226", "0.80", LensColorOption.Family.SOLID, "Brown"),
    "80% Green": ("#2E6B4F", "0.80", LensColorOption.Family.SOLID, "Green"),
    "80% Blue":  ("#3B5BA5", "0.80", LensColorOption.Family.SOLID, "Blue"),
    # GRADIENT — no dedicated gradient swatch treatment in the frontend yet,
    # so these render as a flat "solid" dot at full density.
    "Gradient Brown":  ("#6B4226", "1.00", LensColorOption.Family.SOLID, "Brown"),
    "Gradient Green":  ("#2E6B4F", "1.00", LensColorOption.Family.SOLID, "Green"),
    "Gradient Gray":   ("#808080", "1.00", LensColorOption.Family.SOLID, "Gray"),
    "Gradient Purple": ("#6B4FA0", "1.00", LensColorOption.Family.SOLID, "Purple"),
    "Gradient Blue":   ("#3B5BA5", "1.00", LensColorOption.Family.SOLID, "Blue"),
    # MIRRORED — metallic shine gradient treatment
    "Mirrored Silver": ("#C0C0C0", "1.00", LensColorOption.Family.MIRRORED, "Silver"),
    "Mirrored Blue":   ("#3B5BA5", "1.00", LensColorOption.Family.MIRRORED, "Blue"),
    # POLARIZED — horizontal-banding treatment
    "Polarized Green": ("#2E6B4F", "1.00", LensColorOption.Family.POLARIZED, "Green"),
    "Polarized Gray":  ("#808080", "1.00", LensColorOption.Family.POLARIZED, "Gray"),
    "Polarized Brown": ("#6B4226", "1.00", LensColorOption.Family.POLARIZED, "Brown"),
    # PHOTOCHROMIC — clear-to-tint gradient treatment ("Grey", not "Gray" —
    # matches PHOTOCHROMIC_COLORS's own spelling)
    "Grey":   ("#808080", "1.00", LensColorOption.Family.PHOTOCHROMIC, "Grey"),
    "Brown":  ("#6B4226", "1.00", LensColorOption.Family.PHOTOCHROMIC, "Brown"),
    "Pink":   ("#D98CA8", "1.00", LensColorOption.Family.PHOTOCHROMIC, "Pink"),
    "Purple": ("#6B4FA0", "1.00", LensColorOption.Family.PHOTOCHROMIC, "Purple"),
    "Blue":   ("#3B5BA5", "1.00", LensColorOption.Family.PHOTOCHROMIC, "Blue"),
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

# Recommendation rows are built from STEEP_MERIDIAN_BRACKETS in pricing.py
# so a re-seed cannot put the old spherical-equivalent brackets back.


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
                # tier stays in the lookup key: the unique constraint is
                # (lens_type, index_value, tier), so two rows can share an index.
                LensIndexOption.objects.update_or_create(
                    lens_type=lens_type, index_value=Decimal(index_value), tier=tier,
                    defaults=dict(option_label=label, price=price,
                                  notes=INDEX_RATIONALE.get(index_value, ""),
                                  sort_order=sort_idx * 10, is_active=True),
                )

        # Reader gets exactly one fixed, free index — no interactive Material step.
        LensIndexOption.objects.update_or_create(
            lens_type=lens_types["READER"], index_value=Decimal("1.50"), tier="Reader",
            defaults=dict(option_label="Reader Index", price=D("0"),
                          sort_order=10, is_active=True),
        )
        self._deactivate_retired_index_options()

    def _deactivate_retired_index_options(self):
        """Turn Driving 1.61, Safety 1.59, and Elite 1.71 back off.

        Removing them from INDEX_TIERS_* stops a re-seed from creating them.
        This also catches a row an older seed already created, matched by
        name and index rather than by id. The row is kept for old orders.
        """
        for index_value, needles in RETIRED_INDEX_OPTIONS:
            for row in LensIndexOption.objects.filter(index_value=index_value, is_active=True):
                blob = f"{row.tier} {row.option_label}".lower()
                if any(needle in blob for needle in needles):
                    row.is_active = False
                    row.save(update_fields=["is_active"])

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
                                  sort_order=sort_idx * 10, is_active=True,
                                  **self._swatch_defaults(color_name)),
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
                                      sort_order=sort_idx * 10, is_active=True,
                                      **self._swatch_defaults(color_name)),
                    )

    def _swatch_defaults(self, color_name):
        """swatch_hex/density/family/base_color for one color_name, from
        COLOR_SWATCH_INFO — falls back to a blank hex (plain gray placeholder
        dot, today's behavior) for any color_name not in the table, so a
        future new color doesn't silently crash the seed."""
        info = COLOR_SWATCH_INFO.get(color_name)
        if not info:
            return dict(swatch_hex="", swatch_density=D("1.00"),
                        swatch_family=LensColorOption.Family.SOLID, base_color="")
        hex_value, density, family, base_color = info
        return dict(swatch_hex=hex_value, swatch_density=D(density),
                    swatch_family=family, base_color=base_color)

    def _index_values_for(self, lens_type):
        """All active index_value strings for this Lens Type — used as
        available_index_values on colors that have no narrower, specific
        restriction. NOT an empty list — an empty list would mean
        'available at zero index values' to the workflow API, the
        opposite of what's intended here."""
        # dict.fromkeys dedupes while keeping order, in case two tiers share an index.
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
        # Replace every stored bracket, including the old sign-specific
        # spherical-equivalent rows. The live step does not read these;
        # they mirror the steep-meridian table for the admin.
        LensIndexRecommendationRule.objects.filter(
            category__in=[
                LensIndexRecommendationRule.Category.SINGLE_VISION,
                LensIndexRecommendationRule.Category.BIFOCAL_PROGRESSIVE,
            ],
        ).delete()
        categories = [
            LensIndexRecommendationRule.Category.SINGLE_VISION,
            LensIndexRecommendationRule.Category.BIFOCAL_PROGRESSIVE,
        ]
        for category in categories:
            for sort_idx, (limit, canonical) in enumerate(STEEP_MERIDIAN_BRACKETS, start=1):
                recommended = "1.61" if canonical == D("1.60") else f"{canonical:.2f}"
                LensIndexRecommendationRule.objects.create(
                    category=category,
                    direction="",
                    sort_order=sort_idx * 10,
                    max_combined_power=limit,
                    available_index_values=available_index_labels(canonical),
                    recommended_index_value=recommended,
                    notes="Absolute steep meridian. Recommended SE is not used.",
                )
