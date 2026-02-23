from django.db import models

__all__ = [
    "LensStep",
    "LensOption",
    "LensStepRule",
    "LensOptionAvailability",
]


class TimeStampedModel(models.Model):
    """
    Reusable base model for created/updated timestamps.
    """
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class LensStep(TimeStampedModel):
    """
    Defines the steps in the lens selection workflow, in display order.

    What stpes exists, what order they appear in, whether a stpe is active.

    Examples:
    - COLOR_TYPE
    - COLOR
    - INDEX
    - COATING
    """
    class StepCode(models.TextChoices):
        COLOR_TYPE = "COLOR_TYPE", "Color Type"
        COLOR = "COLOR", "Color"
        INDEX = "INDEX", "Index"
        COATING = "COATING", "Coating"

    code = models.CharField(
        max_length=50,
        choices=StepCode.choices,
        unique=True,
    )  # Step identifier
    label = models.CharField(
        max_length=100,
        help_text="Display label shown to users (can be changed in admin).",
    )  # UI display text
    # Optional description for admin/help text
    description = models.TextField(blank=True)
    sort_order = models.PositiveIntegerField(
        default=0)  # Controls display order of steps
    # Turn a step on/off in admin
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "LensStep"
        verbose_name = "Lens Step"
        verbose_name_plural = "Lens Steps"
        ordering = ["sort_order", "id"]

    def __str__(self):
        return f"{self.label} ({self.code})"


class LensOption(TimeStampedModel):
    """
    Generic table for all selectable lens options across all steps.

    Examples:
    - COLOR_TYPE: Clear, Blue Light Filtering, Sun/Tinted, Light Adjusting
    - COLOR: Gray 50%, Brown 80%, Green Polarized
    - INDEX: 1.56, 1.60, 1.67
    - COATING: AR Coating, Hydrophobic, Oleophobic
    """
    class OptionType(models.TextChoices):
        COLOR_TYPE = "COLOR_TYPE", "Color Type"
        COLOR = "COLOR", "Color"
        INDEX = "INDEX", "Index"
        COATING = "COATING", "Coating"

    # Stable internal code for frontend / API logic (do not change casually)
    code = models.CharField(
        max_length=100,
        unique=True,
        help_text="Stable internal code, e.g. CLEAR, BLUE_LIGHT, SUN_TINTED, INDEX_167, AR_PREMIUM",
    )

    # Human-readable label shown in UI
    name = models.CharField(max_length=100)

    option_type = models.CharField(
        max_length=50,
        choices=OptionType.choices,
        db_index=True,
    )

    description = models.TextField(blank=True)

    add_on_price = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=0,
        help_text="Additional price for selecting this option.",
    )

    image_url = models.CharField(
        max_length=4096,
        blank=True,
        default="",
        help_text="Optional image / preview / swatch URL.",
    )

    # Optional flexible metadata for future expansion
    # Example:
    # {
    #   "tint_family": "solid",
    #   "hex": "#5d6a7a",
    #   "swatch_image_url": "...",
    #   "preview_image_url": "...",
    #   "badge": "Popular"
    # }
    metadata = models.JSONField(
        blank=True,
        default=dict,
        help_text="Optional structured metadata for frontend rendering.",
    )

    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "LensOption"
        verbose_name = "Lens Option"
        verbose_name_plural = "Lens Options"
        ordering = ["option_type", "sort_order", "id"]
        indexes = [
            models.Index(fields=["option_type", "is_active", "sort_order"]),
            models.Index(fields=["code"]),
        ]

    def __str__(self):
        return f"{self.name} [{self.option_type}]"


class LensStepRule(TimeStampedModel):
    """
    Controls workflow transitions (what next step should be shown after selecting an option).

    Example rules:
    - current_step=COLOR_TYPE, selected_option=CLEAR        -> next_step=INDEX
    - current_step=COLOR_TYPE, selected_option=BLUE_LIGHT   -> next_step=INDEX
    - current_step=COLOR_TYPE, selected_option=SUN_TINTED   -> next_step=COLOR
    - current_step=COLOR_TYPE, selected_option=LIGHT_ADJ    -> next_step=COLOR
    - current_step=COLOR, selected_option=GRAY_50          -> next_step=INDEX
    - current_step=INDEX, selected_option=INDEX_167        -> next_step=COATING
    """
    current_step = models.ForeignKey(
        LensStep,
        on_delete=models.CASCADE,
        related_name="outgoing_rules",
    )

    selected_option = models.ForeignKey(
        LensOption,
        on_delete=models.CASCADE,
        related_name="step_rules",
        help_text="The option chosen at the current step.",
    )

    next_step = models.ForeignKey(
        LensStep,
        on_delete=models.CASCADE,
        related_name="incoming_rules",
    )

    # Priority helps if you later add more complex/overlapping rules
    priority = models.PositiveIntegerField(default=0)

    is_active = models.BooleanField(default=True)

    notes = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        db_table = "LensStepRule"
        verbose_name = "Lens Step Rule"
        verbose_name_plural = "Lens Step Rules"
        ordering = ["current_step__sort_order", "priority", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["current_step", "selected_option"],
                name="uq_lens_step_rule_current_step_selected_option",
            )
        ]
        indexes = [
            models.Index(fields=["current_step", "is_active"]),
            models.Index(fields=["selected_option", "is_active"]),
        ]

    def clean(self):
        # Optional consistency validation:
        # selected_option.option_type should usually match current_step.code
        # e.g. current_step=COLOR_TYPE => selected_option.option_type=COLOR_TYPE
        # This is not enforced at DB level but should be validated in forms/admin.
        pass

    def __str__(self):
        return f"{self.current_step.code} + {self.selected_option.code} -> {self.next_step.code}"


class LensOptionAvailability(TimeStampedModel):
    """
    Defines which child options are available after selecting a parent option.

    This powers conditional option lists for the next step.

    Examples:
    - parent_option=SUN_TINTED -> child_option=GRAY_50
    - parent_option=SUN_TINTED -> child_option=BROWN_80
    - parent_option=CLEAR      -> child_option=INDEX_156
    - parent_option=CLEAR      -> child_option=INDEX_160
    - parent_option=GRAY_50    -> child_option=INDEX_156
    - parent_option=INDEX_167  -> child_option=AR_PREMIUM
    """
    parent_option = models.ForeignKey(
        LensOption,
        on_delete=models.CASCADE,
        related_name="available_children",
    )

    child_option = models.ForeignKey(
        LensOption,
        on_delete=models.CASCADE,
        related_name="available_from_parents",
    )

    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    # Optional notes for admin users
    notes = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        db_table = "LensOptionAvailability"
        verbose_name = "Lens Option Availability"
        verbose_name_plural = "Lens Option Availabilities"
        ordering = ["sort_order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["parent_option", "child_option"],
                name="uq_lens_option_availability_parent_child",
            ),
            models.CheckConstraint(
                check=~models.Q(parent_option=models.F("child_option")),
                name="ck_lens_option_availability_no_self_reference",
            ),
        ]
        indexes = [
            models.Index(fields=["parent_option", "is_active", "sort_order"]),
            models.Index(fields=["child_option", "is_active"]),
        ]

    def __str__(self):
        return f"{self.parent_option.code} -> {self.child_option.code}"
