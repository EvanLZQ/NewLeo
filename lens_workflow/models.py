from django.db import models

__all__ = [
    "LensType",
    "LensFunctionPath",
    "LensIndexOption",
    "LensColorOption",
    "LensCoating",
    "LensIndexRecommendationRule",
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
        help_text="False for NON-PRESCRIPTION — frontend uses this to skip the Prescription step.",
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
    Step 2 (+ 2.1): one selectable (Lens Type, Function[, Sun Type]) combination.

    Sun Type is a sub-classifier that only exists when function_code == SUN,
    and only for some Lens Types (e.g. Bifocal has a single undifferentiated
    SUN row with sun_type == "").
    """
    class FunctionCode(models.TextChoices):
        CLEAR = "CLEAR", "Clear"
        SUN = "SUN", "Sun"
        LIGHT_ADJUSTING = "LIGHT_ADJUSTING", "Light Adjusting"

    class SunType(models.TextChoices):
        SOLID = "SOLID", "Solid"
        POLARIZED_MIRRORED = "POLARIZED_MIRRORED", "Polarized / Mirrored"

    lens_type = models.ForeignKey(
        LensType, on_delete=models.CASCADE, related_name="function_paths")

    function_code = models.CharField(
        max_length=50, choices=FunctionCode.choices)
    function_label = models.CharField(max_length=100)
    function_description = models.TextField(blank=True)

    sun_type = models.CharField(
        max_length=30, choices=SunType.choices, blank=True, default="")

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
    Step 3: one selectable index/tier option within a function path.

    Price already reflects the (Lens Type, Function, Sun Type) context via
    the function_path FK — no combination math needed elsewhere.
    """
    function_path = models.ForeignKey(
        LensFunctionPath, on_delete=models.CASCADE, related_name="index_options")

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
        ordering = ["function_path__sort_order", "sort_order", "id"]
        indexes = [
            models.Index(fields=["function_path", "is_active", "sort_order"]),
        ]

    def __str__(self):
        return f"{self.function_path} / {self.option_label}"


class LensColorOption(TimeStampedModel):
    """
    Step 3.1 (conditional): one selectable color for a specific index option.
    """
    index_option = models.ForeignKey(
        LensIndexOption, on_delete=models.CASCADE, related_name="color_options")

    color_name = models.CharField(max_length=100)
    extra_price = models.DecimalField(
        max_digits=8, decimal_places=2, default=0)

    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "LensColorOption"
        verbose_name = "Lens Color Option"
        verbose_name_plural = "Lens Color Options"
        ordering = ["index_option__sort_order", "sort_order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["index_option", "color_name"],
                name="uq_lens_color_option_index_color",
            ),
        ]
        indexes = [
            models.Index(fields=["index_option", "is_active", "sort_order"]),
        ]

    def __str__(self):
        return f"{self.index_option} / {self.color_name}"


class LensCoating(TimeStampedModel):
    """
    Step 4: global coating options, not scoped to Lens Type. Single-select.
    """
    class Code(models.TextChoices):
        NO_AR = "NO_AR", "No AR Coating"
        STANDARD_AR = "STANDARD_AR", "Standard AR Coating"
        PREMIUM_AR = "PREMIUM_AR", "Premium AR Coating"
        BLUE_LIGHT_FILTERING = "BLUE_LIGHT_FILTERING", "Blue Light Filtering"
        HYDRO = "HYDRO", "Hydrophobic"
        OLEO = "OLEO", "Oleophobic"

    code = models.CharField(max_length=50, unique=True, choices=Code.choices)
    label = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=8, decimal_places=2, default=0)
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


class LensIndexRecommendationRule(TimeStampedModel):
    """
    Maps a combined-power bracket (|sphere|+|cylinder|, worse eye) to which
    index values are selectable and which one is recommended, for the Index
    step's recommend-first / expand-to-see-all UI.

    Source: 镜片折射率推荐规则.xlsx. "1.60" in that sheet maps to the real
    product index value "1.61", and "1.71" maps to "1.74" — confirmed with
    the business owner, since only 1.61/1.74 are ever sold as real products.
    """
    class Category(models.TextChoices):
        SINGLE_VISION = "SINGLE_VISION", "Single Vision"
        BIFOCAL_PROGRESSIVE = "BIFOCAL_PROGRESSIVE", "Bifocal / Progressive"

    category = models.CharField(max_length=30, choices=Category.choices)
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
