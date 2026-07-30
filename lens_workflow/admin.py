from django.contrib import admin

from .models import (
    LensType,
    LensFunctionPath,
    LensIndexOption,
    LensColorOption,
    LensCoating,
    LensIndexRecommendationRule,
)


# ---------- Inlines ----------

class LensFunctionPathInline(admin.TabularInline):
    model = LensFunctionPath
    extra = 0
    fields = ("function_code", "function_label", "sun_type",
              "color_required", "extra_price", "sort_order", "is_active")
    ordering = ("sort_order", "id")


class LensIndexOptionInline(admin.TabularInline):
    model = LensIndexOption
    extra = 0
    fields = ("tier", "option_label", "index_value",
              "price", "sort_order", "is_active")
    ordering = ("sort_order", "id")


class LensColorOptionInline(admin.TabularInline):
    model = LensColorOption
    extra = 0
    fields = ("color_name", "extra_price", "sort_order", "is_active")
    ordering = ("sort_order", "id")


# ---------- Admin registrations ----------

@admin.register(LensType)
class LensTypeAdmin(admin.ModelAdmin):
    list_display = ("label", "code", "is_prescription_required",
                     "index_recommendation_category", "sort_order", "is_active", "updated_at")
    list_filter = ("is_prescription_required",
                   "index_recommendation_category", "is_active")
    search_fields = ("label", "code", "description")
    ordering = ("sort_order", "id")
    inlines = [LensFunctionPathInline]


@admin.register(LensFunctionPath)
class LensFunctionPathAdmin(admin.ModelAdmin):
    list_display = ("lens_type", "function_code", "sun_type",
                     "color_required", "extra_price", "sort_order", "is_active", "updated_at")
    list_filter = ("lens_type", "function_code", "sun_type", "is_active")
    search_fields = ("function_label", "function_description",
                      "notes", "lens_type__label", "lens_type__code")
    autocomplete_fields = ("lens_type",)
    ordering = ("lens_type__sort_order", "sort_order", "id")
    inlines = [LensIndexOptionInline, LensColorOptionInline]


@admin.register(LensIndexOption)
class LensIndexOptionAdmin(admin.ModelAdmin):
    list_display = ("function_path", "tier", "option_label",
                     "index_value", "price", "sort_order", "is_active", "updated_at")
    list_filter = ("tier", "is_active", "function_path__lens_type")
    search_fields = ("option_label", "notes",
                      "function_path__function_code", "function_path__lens_type__label")
    autocomplete_fields = ("function_path",)
    ordering = ("function_path__sort_order", "sort_order", "id")


@admin.register(LensColorOption)
class LensColorOptionAdmin(admin.ModelAdmin):
    list_display = ("function_path", "color_name",
                     "extra_price", "sort_order", "is_active", "updated_at")
    list_filter = ("is_active", "function_path__lens_type",
                   "function_path__function_code")
    search_fields = ("color_name", "function_path__function_code",
                      "function_path__lens_type__label")
    autocomplete_fields = ("function_path",)
    ordering = ("function_path__sort_order", "sort_order", "id")


@admin.register(LensCoating)
class LensCoatingAdmin(admin.ModelAdmin):
    list_display = ("label", "code", "price", "is_recommended",
                     "sort_order", "is_active", "updated_at")
    list_filter = ("is_recommended", "is_active")
    search_fields = ("label", "code", "description")
    ordering = ("sort_order", "id")


@admin.register(LensIndexRecommendationRule)
class LensIndexRecommendationRuleAdmin(admin.ModelAdmin):
    list_display = ("category", "max_combined_power", "available_index_values",
                     "recommended_index_value", "sort_order", "updated_at")
    list_filter = ("category",)
    ordering = ("category", "sort_order")
