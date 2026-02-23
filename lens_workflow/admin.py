from django.contrib import admin
from django.core.exceptions import ValidationError
from django.forms import ModelForm

from .models import (
    LensStep,
    LensOption,
    LensStepRule,
    LensOptionAvailability,
)


# ---------- Forms (for admin validation) ----------

class LensStepRuleAdminForm(ModelForm):
    class Meta:
        model = LensStepRule
        fields = "__all__"

    def clean(self):
        cleaned = super().clean()
        current_step = cleaned.get("current_step")
        selected_option = cleaned.get("selected_option")

        if current_step and selected_option:
            # Enforce step/option type consistency:
            # current_step.code should match selected_option.option_type
            if current_step.code != selected_option.option_type:
                raise ValidationError(
                    "Selected option type must match current step code. "
                    f"Got step={current_step.code}, option_type={selected_option.option_type}."
                )
        return cleaned


class LensOptionAvailabilityAdminForm(ModelForm):
    class Meta:
        model = LensOptionAvailability
        fields = "__all__"

    def clean(self):
        cleaned = super().clean()
        parent_option = cleaned.get("parent_option")
        child_option = cleaned.get("child_option")

        if parent_option and child_option:
            if parent_option_id := getattr(parent_option, "id", None):
                if child_option_id := getattr(child_option, "id", None):
                    if parent_option_id == child_option_id:
                        raise ValidationError(
                            "Parent and child option cannot be the same.")

            # Optional safety rules to keep graph sane:
            # Parent/child should not be the same option_type in most cases,
            # except COLOR_TYPE -> COLOR_TYPE is not needed here.
            # We allow all combinations because some future workflows may require it.

        return cleaned


# ---------- Inlines ----------

class LensStepRuleInline(admin.TabularInline):
    """
    When editing a step, quickly define transitions:
    current_step + selected_option -> next_step
    """
    model = LensStepRule
    form = LensStepRuleAdminForm
    fk_name = "current_step"
    extra = 1
    autocomplete_fields = ("selected_option", "next_step")
    fields = ("selected_option", "next_step", "priority", "is_active", "notes")
    ordering = ("priority", "id")


class LensOptionAvailabilityInline(admin.TabularInline):
    """
    When editing an option, define what child options become available.
    Example:
      SUN_TINTED -> GRAY_50, BROWN_80, G15_GREEN
      CLEAR -> INDEX_156, INDEX_160
    """
    model = LensOptionAvailability
    form = LensOptionAvailabilityAdminForm
    fk_name = "parent_option"
    extra = 1
    autocomplete_fields = ("child_option",)
    fields = ("child_option", "sort_order", "is_active", "notes")
    ordering = ("sort_order", "id")


class LensStepOutgoingRuleInline(admin.TabularInline):
    """
    Alternative view when editing an option:
    Show all workflow rules where this option is the selected option.
    """
    model = LensStepRule
    form = LensStepRuleAdminForm
    fk_name = "selected_option"
    extra = 0
    autocomplete_fields = ("current_step", "next_step")
    fields = ("current_step", "next_step", "priority", "is_active", "notes")
    ordering = ("current_step", "priority", "id")
    verbose_name = "Step Rule using this option"
    verbose_name_plural = "Step Rules using this option"


# ---------- Admin registrations ----------

@admin.register(LensStep)
class LensStepAdmin(admin.ModelAdmin):
    list_display = ("label", "code", "sort_order", "is_active", "updated_at")
    list_filter = ("is_active", "code")
    search_fields = ("label", "code", "description")
    ordering = ("sort_order", "id")
    inlines = [LensStepRuleInline]


@admin.register(LensOption)
class LensOptionAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "code",
        "option_type",
        "add_on_price",
        "sort_order",
        "is_active",
        "updated_at",
    )
    list_filter = ("option_type", "is_active")
    search_fields = ("name", "code", "description")
    ordering = ("option_type", "sort_order", "id")
    autocomplete_fields = ()
    inlines = [LensOptionAvailabilityInline, LensStepOutgoingRuleInline]

    fieldsets = (
        ("Basic", {
            "fields": ("code", "name", "option_type", "description")
        }),
        ("Pricing & Media", {
            "fields": ("add_on_price", "image_url")
        }),
        ("UI / Metadata", {
            "fields": ("metadata", "sort_order", "is_active")
        }),
    )


@admin.register(LensStepRule)
class LensStepRuleAdmin(admin.ModelAdmin):
    form = LensStepRuleAdminForm
    list_display = (
        "current_step",
        "selected_option",
        "next_step",
        "priority",
        "is_active",
        "updated_at",
    )
    list_filter = ("is_active", "current_step", "next_step")
    search_fields = (
        "current_step__code",
        "current_step__label",
        "selected_option__code",
        "selected_option__name",
        "next_step__code",
        "next_step__label",
        "notes",
    )
    autocomplete_fields = ("current_step", "selected_option", "next_step")
    ordering = ("current_step__sort_order", "priority", "id")


@admin.register(LensOptionAvailability)
class LensOptionAvailabilityAdmin(admin.ModelAdmin):
    form = LensOptionAvailabilityAdminForm
    list_display = (
        "parent_option",
        "child_option",
        "sort_order",
        "is_active",
        "updated_at",
    )
    list_filter = ("is_active", "parent_option__option_type",
                   "child_option__option_type")
    search_fields = (
        "parent_option__code",
        "parent_option__name",
        "child_option__code",
        "child_option__name",
        "notes",
    )
    autocomplete_fields = ("parent_option", "child_option")
    ordering = ("parent_option__option_type",
                "parent_option__sort_order", "sort_order", "id")
