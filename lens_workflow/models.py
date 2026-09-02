from django.db import models

__all__ = [
    "LensType",
    "LensFunctionPath",
    "LensIndexOption",
    "LensColorOption",
    "LensCoating",
    "LensIndexRecommendationRule",
    "LensReaderStrength",
]


class TimeStampedModel(models.Model):
    """
    Reusable base model for created/updated timestamps.
    """
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class LensType(TimeStampedModel):
    """
    Step 1: the top-level lens category.

    Examples:
    - SINGLE VISION - DISTANCE
    - SINGLE VISION - READING
    - BIFOCAL - WITH A LINE
    - PROGRESSIVE - NO LINE
    - NON-PRESCRIPTION
    """
    code = models.CharField(max_length=50, unique=True)
    label = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    is_prescription_required = models.BooleanField(
        default=True,
        help_text="False for NON-PRESCRIPTION and READER — frontend uses this to skip the Prescription step.",
    )
    is_reader = models.BooleanField(
        default=False,
        help_text="True only for the readymade-readers Lens Type. Routes to a dedicated "
                  "Reader Strength step instead of Prescription, and skips Function/Tint/"
                  "Color/Material/Coating entirely — straight to the review/complete step. "
                  "This is a structural routing flag, not a price/tier — unlike everything "
                  "else in this app it's meant to stay a fixed code branch, not admin data.",
    )

    class IndexRecommendationCategory(models.TextChoices):
        SINGLE_VISION = "SINGLE_VISION", "Single Vision"
        BIFOCAL_PROGRESSIVE = "BIFOCAL_PROGRESSIVE", "Bifocal / Progressive"

    index_recommendation_category = models.CharField(
        max_length=30,
        choices=IndexRecommendationCategory.choices,
        blank=True,
        default="",
        help_text="Blank for lens types with no index recommendation (e.g. Non-Prescription).",
    )

    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "LensType"
        verbose_name = "Lens Type"
        verbose_name_plural = "Lens Types"
        ordering = ["sort_order", "id"]

    def __str__(self):
        return f"{self.label} ({self.code})"


class LensFunctionPath(TimeStampedModel):
    """
    Step 2 (+ 2.1): one selectable (Lens Type, Function[, Tint Type]) combination.

    Tint Type (the sun_type field) is a sub-classifier that only exists when
    function_code == SUN, and only for some Lens Types (e.g. Bifocal doesn't
    offer Sun at all). It's a priced tier in its own right — its extra_price
    stacks on top of the SUN row's own extra_price, it does not replace it.

    LIGHT_ADJUSTING was renamed to PHOTOCHROMIC — same real product ("light-
    responsive" lenses), the mind map's naming just won out.
    """
    class FunctionCode(models.TextChoices):
        CLEAR = "CLEAR", "Clear"
        BLUE_LIGHT_FILTERING = "BLUE_LIGHT_FILTERING", "Blue Light Filtering"
        PHOTOCHROMIC = "PHOTOCHROMIC", "Light-responsive / Photochromic"
        SUN = "SUN", "Sun"

    class SunType(models.TextChoices):
        SOLID = "SOLID", "Solid"
        GRADIENT = "GRADIENT", "Gradient"
        MIRRORED = "MIRRORED", "Mirrored"
        POLARIZED = "POLARIZED", "Polarized"

    lens_type = models.ForeignKey(
        LensType, on_delete=models.CASCADE, related_name="function_paths")

    function_code = models.CharField(
        max_length=50, choices=FunctionCode.choices)
    function_label = models.CharField(max_length=100)
    function_description = models.TextField(blank=True)

    sun_type = models.CharField(
        max_length=30, choices=SunType.choices, blank=True, default="",
        help_text="Tint type — only set when function_code == SUN. Field name kept as "
                  "sun_type for continuity with existing code; conceptually this is the "
                  "workflow's 'Tint Type' step.",
    )

    color_required = models.BooleanField(default=False)

    extra_price = models.DecimalField(
        max_digits=8, decimal_places=2, default=0,
        help_text="Step 2 extra price (currently 0 for every row in the reference guide).",
    )

    notes = models.CharField(max_length=255, blank=True, default="")
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "LensFunctionPath"
        verbose_name = "Lens Function Path"
        verbose_name_plural = "Lens Function Paths"
        ordering = ["lens_type__sort_order", "sort_order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["lens_type", "function_code", "sun_type"],
                name="uq_lens_function_path",
            ),
        ]
        indexes = [
            models.Index(fields=["lens_type", "is_active", "sort_order"]),
            models.Index(fields=["function_code", "is_active"]),
        ]

    def __str__(self):
        suffix = f" / {self.sun_type}" if self.sun_type else ""
        return f"{self.lens_type.code} / {self.function_code}{suffix}"


class LensIndexOption(TimeStampedModel):
    """
    Step 3 (Lens Material): one selectable index/tier option.

    Scoped to LensType, not LensFunctionPath — the reference data confirms
    the same index list and prices apply no matter which Function was
    chosen within a Lens Type (Classic/Blue-light-filtering/Photochromic/Sun
    all lead into the identical Material step). Function's own extra_price
    stacks on top of whichever index gets picked here; they're priced
    independently, not as a combined matrix.

    Reader doesn't get an interactive Material step, but still gets exactly
    one LensIndexOption row (its Lens Type just has a single active row) —
    no separate "reader index" model needed, this falls out naturally.
    """
    lens_type = models.ForeignKey(
        LensType, on_delete=models.CASCADE, related_name="index_options")

    tier = models.CharField(max_length=50)
    option_label = models.CharField(max_length=150)
    index_value = models.DecimalField(max_digits=4, decimal_places=2)
    price = models.DecimalField(max_digits=8, decimal_places=2)

    notes = models.CharField(max_length=255, blank=True, default="")
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "LensIndexOption"
        verbose_name = "Lens Index Option"
        verbose_name_plural = "Lens Index Options"
        ordering = ["lens_type__sort_order", "sort_order", "id"]
        constraints = [
            # tier joins the key (not just lens_type + index_value) so a
            # single refractive index can have more than one priced variant
            # under the same Lens Type — e.g. SVD's plain "1.61 Popular" vs
            # "1.61 Driving" (same index, different product/coating), added
            # for the new pricing sheet. They deliberately share
            # index_value so anything filtering by index (color
            # availability, the recommendation engine) treats them
            # identically — only tier/option_label/price tell them apart.
            models.UniqueConstraint(
                fields=["lens_type", "index_value", "tier"],
                name="uq_lens_index_option_type_value_tier",
            ),
        ]
        indexes = [
            models.Index(fields=["lens_type", "is_active", "sort_order"]),
        ]

    def __str__(self):
        return f"{self.lens_type.code} / {self.option_label}"


class LensColorOption(TimeStampedModel):
    """
    Step 3.1 (conditional): one selectable color, scoped to a function path
    (not to a specific index tier) — the reference data confirms a color's
    extra price never varies by index, so pricing is defined once per
    function path rather than once per index tier. This also lets two
    sibling function paths (e.g. SUN's Solid vs Polarized/Mirrored) show
    their colors together in one merged step, with no separate "pick a sun
    type first" step needed — whichever color the customer picks resolves
    which sibling (and therefore which index price table) applies next.

    Price is uniform across index tiers, but *availability* is not — e.g.
    SVD's Polarized Green/Brown are offered at 1.56/1.61 but drop off at
    1.67. available_index_values records which index_value strings (as they
    appear on LensIndexOption.index_value, e.g. "1.56") this color is
    actually offered at, so the Color step can be filtered to the
    prescription's allowed index bracket, and the following Index step can
    be narrowed to whichever index values the chosen color still supports.
    """
    function_path = models.ForeignKey(
        LensFunctionPath, on_delete=models.CASCADE, related_name="color_options")

    color_name = models.CharField(max_length=100)
    extra_price = models.DecimalField(
        max_digits=8, decimal_places=2, default=0)
    available_index_values = models.JSONField(
        default=list,
        help_text='Index values this color is offered at, e.g. ["1.56", "1.61"]. '
                  "Populated from the Color Compatibility sheet's per-row Index column.",
    )

    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "LensColorOption"
        verbose_name = "Lens Color Option"
        verbose_name_plural = "Lens Color Options"
        ordering = ["function_path__sort_order", "sort_order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["function_path", "color_name"],
                name="uq_lens_color_option_function_color",
            ),
        ]
        indexes = [
            models.Index(fields=["function_path", "is_active", "sort_order"]),
        ]

    def __str__(self):
        return f"{self.function_path} / {self.color_name}"


class LensCoating(TimeStampedModel):
    """
    Step 4 (Coatings): global coating options, not scoped to Lens Type.
    Multi-select with one exception.

    - Anti-scratch / Anti-glare / UV-protection: is_included=True, always
      bundled free with every lens, not a pickable option — shown on the
      Coating step as informational "already included" text.
    - Blue-light-filtering: optional add-on, freely combines with either of
      the pair below (or neither).
    - Oleophobic / Hydrophobic: optional add-ons, but mutually exclusive —
      Hydrophobic already includes Oleophobic's benefit. Both share
      exclusive_group="OLEO_HYDRO"; the workflow API rejects submitting
      more than one coating from the same non-empty exclusive_group.

    Replaces the old No-AR/Standard-AR/Premium-AR tiered single-select
    model entirely — that pricing tier concept doesn't appear anywhere in
    the mind map's coating step.
    """
    class Code(models.TextChoices):
        ANTI_SCRATCH = "ANTI_SCRATCH", "Anti-scratch"
        ANTI_GLARE = "ANTI_GLARE", "Anti-glare"
        UV_PROTECTION = "UV_PROTECTION", "UV Protection"
        BLUE_LIGHT_FILTERING = "BLUE_LIGHT_FILTERING", "Blue Light Filtering"
        OLEOPHOBIC = "OLEOPHOBIC", "Oleophobic"
        HYDROPHOBIC = "HYDROPHOBIC", "Hydrophobic"

    code = models.CharField(max_length=50, unique=True, choices=Code.choices)
    label = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    is_included = models.BooleanField(
        default=False,
        help_text="Always bundled free with every lens — shown as included, not offered as a choice.",
    )
    exclusive_group = models.CharField(
        max_length=50, blank=True, default="",
        help_text="Coatings sharing a non-empty group are mutually exclusive — "
                  "at most one from the group can be selected together.",
    )
    is_recommended = models.BooleanField(default=False)

    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        # NOTE: not "LensCoating" — that db_table name is already taken by
        # the separate legacy Lens.LensCoating model.
        db_table = "LensWorkflowCoating"
        verbose_name = "Lens Coating"
        verbose_name_plural = "Lens Coatings"
        ordering = ["sort_order", "id"]

    def __str__(self):
        return self.label


class LensReaderStrength(TimeStampedModel):
    """
    The only choice a readymade-Reader order makes (see LensType.is_reader).
    No Function/Tint/Color/Material/Coating step follows — strength is
    picked, then straight to review/checkout.
    """
    strength_value = models.DecimalField(
        max_digits=4, decimal_places=2, unique=True,
        help_text='e.g. 1.25 for "+1.25"',
    )
    label = models.CharField(max_length=20, help_text='Display label, e.g. "+1.25"')
    price = models.DecimalField(max_digits=8, decimal_places=2, default=0)

    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "LensReaderStrength"
        verbose_name = "Lens Reader Strength"
        verbose_name_plural = "Lens Reader Strengths"
        ordering = ["sort_order", "id"]

    def __str__(self):
        return self.label


class LensIndexRecommendationRule(TimeStampedModel):
    """
    Maps a combined-power bracket to which index values are selectable and
    which one is recommended, for the Index step's recommend-first /
    expand-to-see-all UI.

    Two different combined-power formulas apply depending on prescription
    sign (see lens_workflow/views.py's _combined_power):
      - Nearsighted (sphere < 0): |sphere| + |cylinder|
      - Farsighted  (sphere >= 0): sphere + cylinder / 2
    Source: the "折射率算法" sheet in Eyelovewear Pricing.xlsx. Bracket
    thresholds/values here are admin-editable data; the formula choice
    above is not — it's a real code branch.

    direction lets a (category, bracket) combo be sign-specific — Single
    Vision has real farsighted-specific bracket data from the pricing
    sheet, so it gets separate NEARSIGHTED/FARSIGHTED rows. Bifocal/
    Progressive has no farsighted-specific data in any source, so its rows
    stay direction="" (blank = matches either sign) — see
    _match_recommendation_rule's fallback for how blank rows are used.
    """
    class Category(models.TextChoices):
        SINGLE_VISION = "SINGLE_VISION", "Single Vision"
        BIFOCAL_PROGRESSIVE = "BIFOCAL_PROGRESSIVE", "Bifocal / Progressive"

    class Direction(models.TextChoices):
        NEARSIGHTED = "NEARSIGHTED", "Nearsighted"
        FARSIGHTED = "FARSIGHTED", "Farsighted"

    category = models.CharField(max_length=30, choices=Category.choices)
    direction = models.CharField(
        max_length=20, choices=Direction.choices, blank=True, default="",
        help_text="Blank = applies to both directions (used where no direction-specific "
                  "bracket data exists). Set when this bracket only applies to one sign.",
    )
    max_combined_power = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        help_text="Upper bound in diopters for |sphere|+|cylinder| (worse eye). "
                  "Null means no upper bound (the last/highest bracket).",
    )
    available_index_values = models.JSONField(
        help_text='Index values selectable in this bracket, e.g. ["1.56", "1.61"].',
    )
    recommended_index_value = models.CharField(max_length=10)
    sort_order = models.PositiveIntegerField(default=0)
    notes = models.TextField(blank=True)

    class Meta:
        db_table = "LensIndexRecommendationRule"
        verbose_name = "Lens Index Recommendation Rule"
        verbose_name_plural = "Lens Index Recommendation Rules"
        ordering = ["category", "sort_order"]

    def __str__(self):
        bound = f"≤{self.max_combined_power}" if self.max_combined_power is not None else "unbounded"
        return f"{self.category} {bound} → recommend {self.recommended_index_value}"
